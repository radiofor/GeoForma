"""Optional, app-owned native inference libraries. UI checks never import Torch."""
import os,re,shutil,stat,sys,uuid,zipfile
from functools import lru_cache
from pathlib import Path,PurePosixPath
from .domain import data_dir
from .distribution import resource_root
from .atomic_io import atomic_json,read_json

_dll_handles=[]
STAGE_MARKER='.geoforma-native-stage'
STAGE_MARKER_CONTENT='GeoForma native installation stage v1\n'

@lru_cache(maxsize=1)
def catalog():return read_json(Path(__file__).with_name('native_runtime_catalog.json'))
def profile(key):
    try:return catalog()['profiles'][key]
    except KeyError:raise ValueError('未知推理运行库配置。') from None
def lightweight():return (resource_root()/'geoforma/optional-runtime.json').is_file()
def bundled_release():return bool(getattr(sys,'frozen',False)) and not lightweight()
def runtime_root():
    from .resource_location import require_resource_dir
    return require_resource_dir(data_dir())/'runtime'/'native-v1'

def bundled_wheel(wheel):
    roots=[resource_root()/'runtime_wheels']
    if not getattr(sys,'frozen',False):roots.append(resource_root()/'environment/resource-wheels')
    return next((root/wheel['filename'] for root in roots if (root/wheel['filename']).is_file()),None)

def download_wheels(key):return [w for w in profile(key)['wheels'] if not bundled_wheel(w)]

def _safe_child(path,root):
    path=Path(path);root=Path(root)
    current=path
    while current!=root.parent:
        if current.is_symlink() or current.is_junction():raise ValueError('运行库目录不能指向外部链接。')
        if current==root:break
        current=current.parent
    if not path.resolve().is_relative_to(root.resolve()):raise ValueError('运行库路径超出管理范围。')
    return path

def _installed_state(state,root):
    try:
        if state.get('kind')!='geoforma-native-installed-v1' or not re.fullmatch(r'[a-f0-9]{32}',state.get('generation','')):return None
        spec=profile(state['profile'])
        if state['wheels']!=[{k:w[k] for k in ('filename','sha256')} for w in spec['wheels']]:return None
        if state['probe'].get('ok') is not True or state['probe'].get('versions')!={w['name']:w['version'] for w in spec['wheels']}:return None
        site=_safe_child(root/state['generation'],root)
        if not (site/'torch/__init__.py').is_file() or not (site/'torchvision/__init__.py').is_file() or not (site/'torch/lib/torch_cpu.dll').is_file():return None
        return state|{'site':str(site)}
    except (OSError,ValueError,KeyError,TypeError,AttributeError):return None

def managed_runtime():
    try:
        root=runtime_root();marker=root/'current.json'
        if not marker.is_file():return None
        _safe_child(marker,root);return _installed_state(read_json(marker),root)
    except (OSError,ValueError):return None


def installed_runtimes():
    """Read current and inactive validated installations, never download caches."""
    current=managed_runtime();states=[current] if current else []
    seen={state.get('generation') for state in states}
    try:
        root=runtime_root()
        _safe_child(root,root)
        for path in root.iterdir():
            if not re.fullmatch('[a-f0-9]{32}',path.name) or path.name in seen or not path.is_dir():continue
            try:
                marker=_safe_child(path/'installed.json',root);state=_installed_state(read_json(marker),root)
                if state:states.append(state);seen.add(state['generation'])
            except (OSError,ValueError):continue
    except (OSError,ValueError):pass
    return states

def activate_path(site):
    """Only model/probe children call this; never swap libraries in a live process."""
    site=Path(site).resolve();location=str(site)
    sys.path[:]=[location]+[p for p in sys.path if p!=location]
    if sys.platform=='win32':
        for folder in (site/'torch/lib',site/'torchvision'):
            if folder.is_dir():_dll_handles.append(os.add_dll_directory(str(folder)))
    return site

def activate():
    # A fully bundled release must never replace its own runtime with an old
    # separately managed installation left by an earlier version.
    if bundled_release():return None
    state=managed_runtime()
    if state:return activate_path(state['site'])
    if lightweight():raise RuntimeError('推理运行库未配置，请打开“设置 → 资源配置”。')
    return None

def status():
    state=None if bundled_release() else managed_runtime()
    if state:return dict(ready=True,source='managed',profile=state['profile'],title=profile(state['profile'])['title'])
    if not lightweight():
        from .execution_policy import native_available
        if native_available('sam2'):return dict(ready=True,source='bundled',title='现有运行环境')
    return dict(ready=False,source='missing',title='未配置')

def wheel_members(archive):
    """No extractall, scripts, .pth, absolute paths, aliases, or arbitrary packages."""
    files=[];names=set();total=0
    for item in archive.infolist():
        name=item.orig_filename;p=PurePosixPath(name)
        parts=name.rstrip('/').split('/')
        reserved={'con','prn','aux','nul',*(f'com{i}' for i in range(1,10)),*(f'lpt{i}' for i in range(1,10))}
        if '\\' in name or '\0' in name or not p.parts or p.is_absolute() or any(x in ('','..','.') or ':' in x or x.endswith((' ','.')) or x.split('.')[0].casefold() in reserved for x in parts):raise ValueError('wheel 包含不安全路径。')
        mode=item.external_attr>>16
        if stat.S_ISLNK(mode):raise ValueError('wheel 不允许符号链接。')
        if item.is_dir():continue
        if p.parts[0] not in ('torch','torchvision','functorch','torchgen') and not p.parts[0].endswith('.dist-info'):raise ValueError('wheel 包含未支持的安装内容。')
        if p.suffix.lower()=='.pth' or '.data' in p.parts[0]:raise ValueError('wheel 不允许安装脚本。')
        key=name.casefold()
        if key in names:raise ValueError('wheel 包含重复路径。')
        names.add(key);total+=item.file_size;files.append(item)
        if total>8*1024**3 or len(files)>40000:raise ValueError('wheel 展开大小超限。')
    return files,total

def _extract(wheel,stage,task):
    from .resource_files import report
    with zipfile.ZipFile(wheel) as archive:
        files,total=wheel_members(archive)
        if shutil.disk_usage(stage).free<total+256*1024**2:raise OSError('运行库安装空间不足。')
        done=0
        for index,item in enumerate(files):
            task.check();target=stage.joinpath(*PurePosixPath(item.filename).parts)
            if target.exists():raise ValueError('多个 wheel 之间存在文件冲突。')
            target.parent.mkdir(parents=True,exist_ok=True)
            with archive.open(item) as src,target.open('xb') as dst:
                while block:=src.read(4*1024**2):
                    task.check();dst.write(block);done+=len(block)
                    report(task,f'安装 · {wheel.name} · {done/1024**2:.1f} / {total/1024**2:.1f} MiB · 文件 {index+1}/{len(files)}',done,total)

class NativeRuntimeManager:
    def install(self,key,task,sources=None):
        from .resource_files import acquire,report
        from .resource_lock import resource_lock as _lock
        from .runtime_probe import probe
        from .resource_location import require_resource_dir
        require_resource_dir(data_dir())
        if sys.implementation.cache_tag!='cpython-313' or sys.platform!='win32':raise ValueError('运行库需要 Windows x64 / Python 3.13。')
        spec=profile(key);root=runtime_root();root.mkdir(parents=True,exist_ok=True);_safe_child(root,root)
        if sources is not None:
            sources={Path(p).name.casefold():Path(p) for p in sources}
            allowed={w['filename'].casefold() for w in spec['wheels']};required={w['filename'].casefold() for w in spec['wheels'] if not bundled_wheel(w)}
            if not required.issubset(sources) or not set(sources).issubset(allowed):raise ValueError('请选择清单中同一配置的外置 wheel，版本和文件名必须匹配。小型配套组件由软件提供。')
        with _lock(root/'install.lock',task):
            def obtain():
                wheels=[]
                for index,w in enumerate(spec['wheels']):
                    scoped=FileTask(task,index+1,len(spec['wheels']))
                    source=(sources.get(w['filename'].casefold()) if sources is not None else None) or bundled_wheel(w)
                    wheels.append(acquire(w,root/'downloads',scoped,source))
                return wheels
            wheels=obtain() if sources is not None else None
            for current in installed_runtimes():
                if not current or current['profile']!=key:continue
                report(task,'验证运行库 · 检查现有配置')
                try:result=probe(current['site'],spec,task)
                except RuntimeError:
                    report(task,'验证运行库 · 原目录未通过检查，重新配置');continue
                state={k:v for k,v in current.items() if k!='site'}|{'probe':result}
                task.check();atomic_json(root/'current.json',state,indent=2)
                report(task,'运行库已就绪',1,1);return state
            wheels=wheels or obtain()
            generation=uuid.uuid4().hex;stage=root/generation;stage.mkdir();_safe_child(stage,root)
            try:
                # Identify interrupted extraction directories without treating
                # unrelated folders as disposable application data.
                (stage/STAGE_MARKER).write_text(STAGE_MARKER_CONTENT,encoding='utf-8')
                for index,wheel in enumerate(wheels):_extract(wheel,stage,FileTask(task,index+1,len(wheels)))
                report(task,'验证运行库 · 启动独立测试进程')
                result=probe(stage,spec,task)
                task.check()
                state=dict(kind='geoforma-native-installed-v1',generation=generation,profile=key,
                    wheels=[{k:w[k] for k in ('filename','sha256')} for w in spec['wheels']],probe=result)
                atomic_json(stage/'installed.json',state,indent=2)
                (stage/STAGE_MARKER).unlink()
                atomic_json(root/'current.json',state,indent=2)
                report(task,'运行库已就绪',1,1)
                return state
            except BaseException:
                _safe_child(stage,root)
                if stage.exists():shutil.rmtree(stage)
                raise

    def clear_downloads(self,task):
        from .resource_lock import resource_lock
        from .resource_files import report
        from .resource_location import require_resource_dir
        require_resource_dir(data_dir())
        root=runtime_root();root.mkdir(parents=True,exist_ok=True);_safe_child(root,root)
        removed=0;count=0
        with resource_lock(root/'install.lock',task):
            folder=_safe_child(root/'downloads',root)
            for spec in catalog()['profiles'].values():
                for wheel in spec['wheels']:
                    path=_safe_child(folder/wheel['filename'],root);task.check()
                    if path.is_file():removed+=path.stat().st_size;path.unlink();count+=1
            report(task,f'下载缓存已清理 · 释放 {removed/1024**2:.1f} MiB',1,1)
        return dict(removed_bytes=removed,files=count,installed_preserved=True)

class FileTask:
    """Adapt shared progress, keeping one cancel owner and no Qt objects here."""
    def __init__(self,task,index,total):
        from types import SimpleNamespace
        self.owner=task;self.cancel_event=task.cancel_event
        self.signals=SimpleNamespace(progress=SimpleNamespace(emit=lambda value,maximum,text:task.signals.progress.emit(value,maximum,f'运行库 {index}/{total} · '+text)))
    def check(self):self.owner.check()
