"""Build a Store submission from a separately frozen native Store channel."""
import argparse,hashlib,json,os,subprocess,sys,zipfile
from pathlib import Path
import xml.etree.ElementTree as ET
from urllib.parse import unquote

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def sdk_tool(name):
    base=Path(os.environ.get('ProgramFiles(x86)','C:/Program Files (x86)'))/'Windows Kits/10/bin'
    versions=sorted((path for path in base.glob('*') if path.name[0].isdigit()),key=lambda path:tuple(int(value) for value in path.name.split('.')),reverse=True)
    return next((path/'x64'/name for path in versions if (path/'x64'/name).is_file()),None)


def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def verify_archived_payload(archive,bundle,records):
    """Verify the bytes actually packaged, including the inventory itself."""
    manifest=Path(bundle)/'release-manifest.json'
    expected={'App/'+row['path']:(row['bytes'],row['sha256'].lower()) for row in records}
    expected['App/release-manifest.json']=(manifest.stat().st_size,sha(manifest))
    # MakeAppx stores OPC part names as URI paths (e.g. %20 and %2B),
    # while the release inventory contains filesystem names.
    entries=[(unquote(item.filename,encoding='utf-8',errors='strict'),item) for item in archive.infolist() if not item.is_dir()]
    entries=[(name,item) for name,item in entries if name.casefold().startswith('app/')]
    names=[name for name,_ in entries]
    if len(names)!=len({name.casefold() for name in names}) or set(names)!=set(expected):
        raise ValueError('MSIX 程序文件与发布清单不一致。')
    for name,item in entries:
        size,digest=expected[name]
        with archive.open(item) as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
        if item.file_size!=size or actual!=digest:raise ValueError('MSIX 程序文件内容校验失败：'+name)
    return len(entries)


def create_store_assets(stage,makepri):
    """Generate shell icons and the index Windows uses to select variants."""
    import tempfile
    from PIL import Image
    from tools.build_icon import fitted_artwork
    source=fitted_artwork(Image.open(ROOT/'assets/geoforma_logo_map_pen.png').convert('RGBA'))
    assets=stage/'StoreAssets';assets.mkdir(exist_ok=True)
    names=[]
    def save(name,size):
        source.resize((size,size),Image.Resampling.LANCZOS).save(assets/name)
        names.append(name)
    for name,size in (('StoreLogo.png',50),('Square44x44Logo.png',44),('Square150x150Logo.png',150)):
        save(name,size)
    for size in (16,20,24,30,32,36,40,48,60,64,72,80,96,256):
        for suffix in ('','_altform-unplated','_altform-lightunplated'):
            save(f'Square44x44Logo.targetsize-{size}{suffix}.png',size)
    for base in (44,150):
        for scale in (200,400):save(f'Square{base}x{base}Logo.scale-{scale}.png',base*scale//100)
    # Index only this build's assets, never unrelated or stale stage files.
    with tempfile.TemporaryDirectory(prefix='geoforma-pri-') as temp:
        root=Path(temp);index_assets=root/'StoreAssets';index_assets.mkdir()
        import shutil
        for name in names:shutil.copyfile(assets/name,index_assets/name)
        config=root/'priconfig.xml';pri=stage/'resources.pri'
        subprocess.run([str(makepri),'createconfig','/cf',str(config),'/dq','zh-CN','/o'],check=True)
        # Keep every scale in the main package instead of separate resource packs.
        tree=ET.parse(config);packaging=tree.getroot().find('packaging')
        if packaging is not None:tree.getroot().remove(packaging)
        tree.write(config,encoding='utf-8',xml_declaration=True)
        subprocess.run([str(makepri),'new','/pr',str(root),'/cf',str(config),'/mn',str(stage/'AppxManifest.xml'),'/of',str(pri),'/o'],check=True)
    return [(assets/name,'StoreAssets/'+name) for name in names]+[(pri,'resources.pri')]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--bundle',type=Path)
    parser.add_argument('--output-dir',type=Path);parser.add_argument('--makeappx',type=Path)
    parser.add_argument('--prepare-only',action='store_true');args=parser.parse_args()
    from geoforma.runtime_profile import activate_security_profile,require_release_security
    activate_security_profile(ROOT)
    from geoforma.distribution import VERSION
    from geoforma.atomic_io import read_json,atomic_json
    from geoforma.msix_package import validate_identity,manifest_bytes,file_mapping,package_version,FOUNDATION
    profile=read_json(ROOT/'packaging/store-profile.json');family=validate_identity(profile)
    work=ROOT/'build'/('msix_'+VERSION.replace('.','_'))
    bundle=(args.bundle or ROOT/'release'/VERSION/'portable/GeoForma').resolve();output=(args.output_dir or ROOT/'release'/VERSION/'store').resolve();stage=work/'package';stage.mkdir(parents=True,exist_ok=True);output.mkdir(parents=True,exist_ok=True)
    if not (bundle/'GeoForma.exe').is_file():raise FileNotFoundError('请先完成商店渠道的原生冻结构建。')
    if read_json(bundle/'_internal/geoforma/store-profile.json')!=profile:raise ValueError('此 EXE 不是匹配的商店渠道构建。')
    release=read_json(bundle/'release-manifest.json')
    from tools.build_release import require_native_release
    require_native_release(bundle,release,VERSION)
    packages=read_json(bundle/'licenses/packages.json');versions={row['name']:row['version'] for row in packages}
    if release.get('runtime_mode')=='optional':
        from geoforma.native_runtime import catalog
        pinned=catalog()
        if read_json(bundle/'_internal/geoforma/native_runtime_catalog.json')!=pinned:raise ValueError('运行库清单不匹配。')
        versions.update({w['name']:w['version'] for w in pinned['profiles']['cpu']['wheels']})
    require_release_security(versions)
    from geoforma.release_artifacts import verify_release_inventory
    verified_files=verify_release_inventory(bundle,release['files'])
    manifest=stage/'AppxManifest.xml';manifest.write_bytes(manifest_bytes(profile,VERSION))
    makepri=sdk_tool('makepri.exe')
    if makepri is None:raise FileNotFoundError('未找到 Windows SDK MakePri.exe。')
    entries=[(manifest,'AppxManifest.xml')]+create_store_assets(stage,makepri)
    entries.extend((path,'App/'+path.relative_to(bundle).as_posix()) for path in sorted(bundle.rglob('*')) if path.is_file())
    mapping=stage/'mapping.txt';mapping.write_text(file_mapping(entries),encoding='utf-8-sig')
    metadata={'identity':profile,'package_version':package_version(VERSION),'application_version':VERSION,'package_family':family,
        'aumid':family+'!'+profile['app_id'],'runtime_behavior':'win32App','trust_level':'mediumIL','capabilities':['runFullTrust'],
        'bundle':str(bundle),'mapping_entries':len(entries),'payload_sha256_verified':True,'verified_payload_files':verified_files,
        'store_signed':False,'local_certificate_required_for_sideload':True}
    atomic_json(output/'package-info.json',metadata,indent=2)
    (output/'AppxManifest.xml').write_bytes(manifest.read_bytes())
    if args.prepare_only:print(json.dumps(metadata));return
    makeappx=args.makeappx or sdk_tool('makeappx.exe')
    if makeappx is None:raise FileNotFoundError('未找到 Windows SDK MakeAppx.exe。')
    package=output/('GeoForma_'+package_version(VERSION)+'_x64.msix')
    subprocess.run([str(makeappx),'pack','/f',str(mapping),'/p',str(package),'/o','/v'],check=True,cwd=stage)
    with zipfile.ZipFile(package) as archive:
        actual=ET.fromstring(archive.read('AppxManifest.xml')).find('{'+FOUNDATION+'}Identity')
        assert actual.attrib=={'Name':profile['identity_name'],'Publisher':profile['publisher'],'Version':package_version(VERSION),'ProcessorArchitecture':'x64'}
        assert 'App/GeoForma.exe' in archive.namelist() and 'AppxBlockMap.xml' in archive.namelist()
        assert 'AppxSignature.p7x' not in archive.namelist()
        metadata['verified_archive_payload_files']=verify_archived_payload(archive,bundle,release['files'])
        metadata['archive_payload_sha256_verified']=True
        metadata['zip_entries']=len(archive.infolist());metadata['manifest_validated']=True
    metadata.update(file=package.name,bytes=package.stat().st_size,sha256=sha(package),makeappx=str(makeappx),semantic_validation=True)
    atomic_json(output/'package-info.json',metadata,indent=2)
    (output/'SHA256SUMS.txt').write_text(metadata['sha256']+'  '+package.name+'\n',encoding='utf-8')
    print(json.dumps({key:metadata[key] for key in ('file','bytes','sha256','package_family','semantic_validation')}),flush=True)


if __name__=='__main__':main()
