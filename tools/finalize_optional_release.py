"""Collate real resource/installer/program acceptance and package identity checks."""
import argparse,hashlib,json,shutil,sys,zipfile
from pathlib import Path
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--release',type=Path,required=True);parser.add_argument('--qa',type=Path,required=True);args=parser.parse_args()
    from geoforma.distribution import VERSION
    from geoforma.atomic_io import read_json,atomic_json
    release=args.release.resolve();source=args.qa.resolve();target=release/'qa';target.mkdir(exist_ok=True)
    suite=ET.parse(source/'full-tests.xml').getroot().find('testsuite')
    assert suite is not None and int(suite.attrib['failures'])==int(suite.attrib['errors'])==0
    reports={}
    for name in ('core_1','core_1.5','missing_runtime','runtime_local','weight_local','inference_cpu','inference_cuda','inference_fallback','runtime_cpu_only','inference_cpu_only','inference_cpu_only_fallback'):
        path=source/'frozen-qa'/(name+'.json');value=read_json(path);assert value['ok'],name
        if 'version' in value:assert value['version']==VERSION
        reports[name]=dict(ok=True,device=value.get('device'),resources=value.get('resources'))
        shutil.copy2(path,target/(name+'.json'))
    automatic=read_json(source/'frozen-auto.json');assert automatic['ok'] and automatic['result']['profile']=='cpu'
    assert any('下载 torch' in item['text'] for item in automatic['progress'])
    shutil.copy2(source/'frozen-auto.json',target/'frozen-auto.json')
    for filename in ('full-tests.xml','final-focused.xml'):
        shutil.copy2(source/filename,target/filename)
    for scale in ('1','1.5'):shutil.copy2(source/'frozen-qa'/('core_'+scale+'.png'),target/('resources_'+scale+'.png'))
    installer=read_json(target/'installer_results.json');assert installer['ok'] and installer['user_data_preserved'] and installer['uninstall']
    package=read_json(release/'store/package-info.json');path=release/'store'/package['file']
    assert package['semantic_validation'] and package['manifest_validated'] and sha(path)==package['sha256'] and path.stat().st_size==package['bytes']
    bundle=release/'portable/GeoForma';manifest=read_json(bundle/'release-manifest.json');assert manifest['runtime_mode']=='optional' and manifest['version']==VERSION
    with zipfile.ZipFile(path) as archive:
        assert 'AppxSignature.p7x' not in archive.namelist()
        assert not any('/models/' in item.filename or item.filename.lower().endswith(('torch_cuda.dll','torch_cpu.dll','cublaslt64_12.dll')) for item in archive.infolist())
        assert len([n for n in archive.namelist() if '/runtime_wheels/' in n and n.endswith('.whl')])==2
    duplicates={}
    for item in manifest['files']:
        if item['path'].lower().endswith('.dll') and item['bytes']>1024**2:duplicates.setdefault((Path(item['path']).name.casefold(),item['sha256']),[]).append(item['path'])
    duplicates=[values for values in duplicates.values() if len(values)>1];assert not duplicates
    for filename in ('zlib.dll','VCRUNTIME140.dll'):assert (bundle/'_internal'/filename).is_file()
    setup=read_json(release/'installer/files.json')
    for item in setup['files']:assert sha(release/'installer'/item['file'])==item['sha256']
    previous=read_json(target/'verification_summary.json') if (target/'verification_summary.json').is_file() else {}
    baseline=previous.get('old_msix_bytes')
    summary=dict(version=VERSION,source_tests=int(suite.attrib['tests']),source_failures=0,
        frozen_program=reports,automatic_cpu_download=True,local_single_pytorch_wheel=True,
        small_companions_bundled=True,ordinary_installer=installer,msix=dict(file=package['file'],bytes=package['bytes'],sha256=package['sha256'],semantic_validation=True),
        portable_bytes=sum(item['bytes'] for item in manifest['files']),installer_bytes=sum(item['bytes'] for item in setup['files']),duplicate_large_dll_groups=0,
        msix_signed_installation_tested=False,store_certification_submitted=False,certificate_trust_changed=False,developer_mode_changed=False,
        limits=['Actual signed-MSIX install/update/uninstall acceptance and Store certification remain separate.'])
    if type(baseline) is int and baseline>0:
        summary.update(old_msix_bytes=baseline,package_reduction_percent=round(100*(1-package['bytes']/baseline),2))
    atomic_json(target/'verification_summary.json',summary,indent=2)
    print(json.dumps({key:summary[key] for key in ('version','source_tests','package_reduction_percent','portable_bytes','installer_bytes') if key in summary},indent=2))

if __name__=='__main__':main()
