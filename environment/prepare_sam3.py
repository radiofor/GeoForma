"""Prepare pinned Meta SAM 3 code with a minimal timm compatibility fix."""
import hashlib,json,shutil,subprocess,sys,tempfile,zipfile
from pathlib import Path,PurePosixPath

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from geoforma.model_catalog import SAM3_COMMIT
from geoforma.network import open_https

PACKAGES=['timm==1.0.17','huggingface-hub==0.36.0','ftfy==6.1.1',
          'requests==2.34.2','urllib3==2.8.0','charset-normalizer==3.4.4','idna==3.20',
          'safetensors==0.6.2','wcwidth==0.2.14','einops==0.8.1','pycocotools==2.0.11',
          'psutil==7.1.1','regex==2025.9.18','tqdm==4.70.1']

PATCH_FILE='model/video_tracking_multiplex.py'
OLD_IMPORT=b'from timm.models.layers import trunc_normal_'
NEW_IMPORT=b'from timm.layers import trunc_normal_'

def runtime_source(relative,original):
    if relative.as_posix()!=PATCH_FILE:return original
    if original.count(OLD_IMPORT)!=1:raise ValueError('SAM 3 官方源码的 timm 导入不符合预期。')
    return original.replace(OLD_IMPORT,NEW_IMPORT,1)

def prepare():
    target=ROOT/'environment'/'sam3-runtime';target.mkdir(parents=True,exist_ok=True)
    source=ROOT/'environment'/'sam_sources'/('sam3-'+SAM3_COMMIT)/'sam3'
    if not source.is_dir():
        (ROOT/'build').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as temporary:
            archive=Path(temporary)/'sam3.zip'
            with open_https('https://github.com/facebookresearch/sam3/archive/'+SAM3_COMMIT+'.zip',timeout=60) as response,archive.open('wb') as output:
                shutil.copyfileobj(response,output)
            with zipfile.ZipFile(archive) as package:
                for member in package.infolist():
                    parts=PurePosixPath(member.filename).parts
                    if '..' in parts or '\\' in member.filename or ':' in member.filename or PurePosixPath(member.filename).is_absolute():raise ValueError('源码压缩包路径无效。')
                    if len(parts)>2 and parts[1]=='sam3' and not member.is_dir():
                        file=source.joinpath(*parts[2:])
                        if not file.resolve().is_relative_to(source.resolve()) or member.file_size>64*1024**2:raise ValueError('源码文件路径或大小无效。')
                        file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(package.read(member))
    package=target/'sam3'
    if not package.exists():shutil.copytree(source,package,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    files={};runtime_files={};patches=[]
    for file in source.rglob('*'):
        if file.is_file() and '__pycache__' not in file.parts and file.suffix!='.pyc':
            relative=file.relative_to(source);installed=package/relative
            original=file.read_bytes();expected=runtime_source(relative,original)
            if not installed.is_file():raise ValueError('SAM 3 运行源码缺失：'+str(relative))
            current=installed.read_bytes()
            if relative.as_posix()==PATCH_FILE and current==original:
                installed.write_bytes(expected);current=expected
            if current!=expected:raise ValueError('SAM 3 运行源码与预期不符：'+str(relative))
            digest=hashlib.sha256(original).hexdigest();runtime_digest=hashlib.sha256(expected).hexdigest()
            files[str(relative)]=digest;runtime_files[str(relative)]=runtime_digest
            if original!=expected:patches.append({'file':relative.as_posix(),'reason':'Use the supported timm.layers import','original_sha256':digest,'runtime_sha256':runtime_digest})
    packages=PACKAGES+(['triton-windows==3.5.1.post21'] if sys.platform=='win32' else ['triton==3.5.1'])
    from importlib.metadata import distributions
    installed={d.metadata['Name'].lower().replace('_','-'):d.version for d in distributions(path=[str(target)])}
    missing=[p for p in packages if installed.get(p.split('==')[0])!=p.split('==')[1]]
    if missing:subprocess.run([sys.executable,'-m','pip','install','--target',str(target),'--no-deps',*missing],check=True)
    (target/'official-source.json').write_text(json.dumps({'repository':'https://github.com/facebookresearch/sam3','commit':SAM3_COMMIT,'files':files,'runtime_files':runtime_files,'patches':patches},indent=2),encoding='utf-8')
    from main import configure_runtime
    configure_runtime()
    from geoforma.sam3_runtime import activate
    activate()
    from sam3.model_builder import build_sam3_image_model
    print('SAM 3 official code and isolated dependencies are ready.')

if __name__=='__main__':prepare()
