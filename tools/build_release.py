"""Build a relocatable offline Windows directory; never copies a user's whole env."""
import argparse,hashlib,importlib.metadata,json,os,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def offline_checkpoint(override=None):
    from geoforma.model_preferences import recommended_model
    from geoforma.model_catalog import model_spec
    config=recommended_model();spec=model_spec(config['variant'],config['backend'])
    weight=Path(override or config['checkpoint'])
    if not weight.is_file() or sha(weight)!=spec['sha256']:raise ValueError('离线发布需提供经校验的默认模型权重：'+spec['title'])
    return spec,weight


def require_native_release(bundle,manifest,version):
    # A previously frozen executable cannot be made native-only by replacing
    # its docs or deleting its optional payload; require a fresh-format build.
    if manifest.get('version')!=version or manifest.get('execution')!='native' or (bundle/'runtime').exists():
        raise ValueError('既有程序不是当前原生版本，请使用新的输出目录并完整重新构建。')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--weight',type=Path);parser.add_argument('--output-dir',type=Path,help='Keep this release in its own directory');parser.add_argument('--work-dir',type=Path,help='Use an isolated PyInstaller work directory');parser.add_argument('--iscc',type=Path);parser.add_argument('--skip-freeze',action='store_true',help='Refresh payload/docs/manifest around an already tested EXE')
    modes=parser.add_mutually_exclusive_group()
    modes.add_argument('--optional-runtime',action='store_true',help='Ship GIS/UI only; inference wheels and weights are configured on demand')
    modes.add_argument('--bundled-runtime-no-weights',action='store_true',help='Bundle inference runtime; configure model weights on demand')
    args=parser.parse_args()
    sys.path.insert(0,str(ROOT));from geoforma.distribution import VERSION
    from geoforma.runtime_profile import activate_security_profile,require_release_security
    activate_security_profile(ROOT);require_release_security()
    from tools.check_dependencies import require_consistent_dependencies
    require_consistent_dependencies()
    from geoforma.release_artifacts import collect_licenses,release_inventory
    from geoforma.model_preferences import recommended_model
    from geoforma.model_catalog import model_spec
    if args.bundled_runtime_no_weights and args.weight:raise ValueError('按需下载权重的构建不接受 --weight。')
    if args.bundled_runtime_no_weights:
        from geoforma.native_runtime import profile
        versions={name:importlib.metadata.version(name) for name in ('torch','torchvision')}
        expected={wheel['name']:wheel['version'] for wheel in profile('cu126')['wheels']}
        if versions!=expected:raise ValueError('内置运行库需要与清单完全匹配的 NVIDIA CUDA 版本。')
    spec,weight=(model_spec('small','sam2.1'),None) if args.optional_runtime or args.bundled_runtime_no_weights else offline_checkpoint(args.weight)
    if args.optional_runtime:
        os.environ['GEOFORMA_OPTIONAL_RUNTIME']='1'
    else:os.environ['GEOFORMA_OPTIONAL_RUNTIME']='0'
    target=(args.output_dir or ROOT/'release'/VERSION).resolve();target.mkdir(parents=True,exist_ok=True)
    if not args.skip_freeze:subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--distpath',str(target/'portable'),'--workpath',str(args.work_dir or ROOT/('build/native-'+VERSION)),str(ROOT/'packaging/geoforma.spec')],cwd=ROOT,check=True)
    else:
        if not (target/'portable/GeoForma/GeoForma.exe').exists():raise FileNotFoundError('Build the EXE before refreshing its release')
        from geoforma.release_artifacts import verify_release_inventory
        from geoforma.atomic_io import read_json
        previous=read_json(target/'portable/GeoForma/release-manifest.json')
        require_native_release(target/'portable/GeoForma',previous,VERSION)
        if bool(previous.get('default_model',{}).get('optional')) != bool(args.optional_runtime or args.bundled_runtime_no_weights):
            raise ValueError('不能在既有程序上变更权重打包模式，请完整构建。')
        verify_release_inventory(target/'portable/GeoForma',previous['files'])
        package_list=target/'portable/GeoForma/licenses/packages.json'
        if not package_list.exists():raise ValueError('既有安装包缺少依赖版本记录，请完整重新打包。')
        versions={row['name']:row['version'] for row in read_json(package_list)}
        optional_marker=target/'portable/GeoForma/_internal/geoforma/optional-runtime.json'
        if optional_marker.is_file()!=args.optional_runtime:raise ValueError('不能在既有程序上变更运行库打包模式，请完整构建。')
        if args.optional_runtime:
            from geoforma.native_runtime import catalog
            versions.update({w['name']:w['version'] for w in catalog()['profiles']['cpu']['wheels']})
        require_release_security(versions)
    bundle=target/'portable/GeoForma'
    if (bundle/'runtime').exists():raise ValueError('既有目录包含旧运行包，请使用新的输出目录并完整重新构建。')
    if weight:
        (bundle/'models').mkdir(exist_ok=True);shutil.copy2(weight,bundle/'models'/spec['file'])
    elif (bundle/'models').exists():raise ValueError('构建目录中存在旧权重，请使用独立的输出目录。')
    shutil.copy2(ROOT/'README.txt',bundle/'README.txt')
    docs=bundle/'docs';docs.mkdir(exist_ok=True);shutil.copy2(ROOT/'docs/DEPLOYMENT.txt',docs/'DEPLOYMENT.txt')
    shutil.copy2(ROOT/'docs/APPEARANCE.txt',docs/'APPEARANCE.txt')
    shutil.copy2(ROOT/'docs/MODELS.txt',docs/'MODELS.txt')
    from geoforma.application_info import DOCUMENTS
    for _,filename in DOCUMENTS:shutil.copy2(ROOT/'docs'/filename,docs/filename)
    licenses=bundle/'licenses';packages=collect_licenses((dist for dist in importlib.metadata.distributions() if not args.optional_runtime or dist.metadata['Name'].casefold() not in ('torch','torchvision')),licenses)
    # The installer incorporates the community Simplified Chinese translation.
    # Preserve the MIT notice alongside the other third-party licenses.
    (licenses/'Inno-Setup-Chinese-Simplified').mkdir(parents=True,exist_ok=True)
    shutil.copy2(ROOT/'packaging'/'ChineseSimplified-LICENSE.txt',licenses/'Inno-Setup-Chinese-Simplified'/'LICENSE.txt')
    from geoforma.model_catalog import SAM3_COMMIT
    sam3_license=ROOT/'environment'/'sam_sources'/('sam3-'+SAM3_COMMIT)/'LICENSE'
    if not sam3_license.is_file():raise FileNotFoundError('缺少 SAM 3 官方许可协议，无法制作发布包。')
    (licenses/'SAM-3').mkdir(parents=True,exist_ok=True);shutil.copy2(sam3_license,licenses/'SAM-3'/'LICENSE')
    (licenses/'packages.json').write_text(json.dumps(packages,indent=2),encoding='utf-8')
    manifest={'version':VERSION,'python':sys.version,'default_model':{'id':spec['id'],'file':'models/'+spec['file'],'sha256':spec['sha256']},'execution':'native','files':[]}
    manifest['files']=release_inventory(bundle)
    manifest['runtime_mode']='optional' if args.optional_runtime else 'bundled'
    if args.optional_runtime or args.bundled_runtime_no_weights:manifest['default_model']['optional']=True
    (bundle/'release-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    (target/'build-info.json').write_text(json.dumps({'version':VERSION,'portable':str(bundle),'bytes':sum(r['bytes'] for r in manifest['files']),'files':len(manifest['files'])},indent=2),encoding='utf-8')
    if args.iscc:subprocess.run([str(args.iscc),'/DAppVersion='+VERSION,'/DBundleDir='+str(bundle),'/DInstallerDir='+str(target/'installer'),*(['/DOptionalRuntime=1'] if args.optional_runtime else []),str(ROOT/'packaging/geoforma.iss')],check=True)
    print('Built',bundle,flush=True)

if __name__=='__main__':main()
