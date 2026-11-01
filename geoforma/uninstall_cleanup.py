"""Conservative cleanup primitives for explicitly selected uninstall data."""
import base64,csv,hashlib,os,re
from pathlib import Path,PurePosixPath

from .project_cache import checked_directory, clear_image_cache


def _owned_runtime(state,generation):
    from .native_runtime import profile
    try:
        spec=profile(state['profile'])
        return (state.get('kind')=='geoforma-native-installed-v1' and state.get('generation')==generation
                and state['wheels']==[{k:w[k] for k in ('filename','sha256')} for w in spec['wheels']]
                and state['probe'].get('ok') is True
                and state['probe'].get('versions')=={w['name']:w['version'] for w in spec['wheels']})
    except (KeyError,TypeError,ValueError,AttributeError):return False


def clean_installed_runtimes(root):
    """Remove verified wheel-record files while preserving unrecognized data."""
    from .atomic_io import read_json
    runtime=checked_directory(root,'runtime/native-v1');removed=[];skipped=[]
    if not runtime.is_dir():return removed,skipped
    def fail(error):raise error
    for generation in runtime.iterdir():
        if not re.fullmatch('[a-f0-9]{32}',generation.name):continue
        if generation.is_symlink() or generation.is_junction() or not generation.is_dir():
            skipped.append(str(generation));continue
        marker=generation/'installed.json'
        try:
            if marker.is_symlink() or marker.is_junction():raise ValueError('运行库标记是链接。')
            state=read_json(marker)
            if not _owned_runtime(state,generation.name):raise ValueError('运行库归属记录无效。')
            records=[]
            for wheel in state['wheels']:
                stem=wheel['filename'].split('-')
                record=checked_directory(generation,stem[0]+'-'+stem[1]+'.dist-info/RECORD')
                if not record.is_file():raise ValueError('运行库文件清单缺失。')
                records.append(record)
            paths=[]
            for record in records:
                with record.open(encoding='utf-8',newline='') as stream:
                    for row in csv.reader(stream):
                        if len(row)!=3:raise ValueError('运行库文件清单无效。')
                        relative=PurePosixPath(row[0])
                        if relative.is_absolute() or any(p in ('.','..') for p in relative.parts) or '\\' in row[0] or ':' in row[0]:raise ValueError('运行库文件清单路径无效。')
                        path=checked_directory(generation,str(relative))
                        if not row[1]:continue
                        if not row[1].startswith('sha256=') or not row[2].isdigit():raise ValueError('运行库文件校验信息无效。')
                        paths.append((path,row[1][7:],int(row[2])))
            for path,digest,size in paths:
                if not path.exists():continue
                if path.is_symlink() or path.is_junction() or not path.is_file() or path.stat().st_size!=size:
                    skipped.append(str(path));continue
                sha=hashlib.sha256()
                with path.open('rb') as stream:
                    for chunk in iter(lambda:stream.read(4*1024*1024),b''):sha.update(chunk)
                if base64.urlsafe_b64encode(sha.digest()).decode().rstrip('=')!=digest:
                    skipped.append(str(path));continue
                path.unlink();removed.append(str(path))
            # RECORD and the ownership marker remain if any unknown file exists.
            remaining=[]
            for folder,dirs,files in os.walk(generation,topdown=False,followlinks=False,onerror=fail):
                directory=Path(folder)
                if directory.is_symlink() or directory.is_junction():remaining.append(str(directory));continue
                for name in files:
                    path=directory/name
                    if path not in records and path!=marker:remaining.append(str(path))
                for name in dirs:
                    path=directory/name
                    if path.is_symlink() or path.is_junction():remaining.append(str(path))
                    else:
                        try:path.rmdir()
                        except OSError:pass
            if remaining:skipped.extend(remaining);continue
            for record in records:record.unlink(missing_ok=True)
            marker.unlink(missing_ok=True)
            for folder,dirs,files in os.walk(generation,topdown=False,followlinks=False,onerror=fail):
                try:Path(folder).rmdir()
                except OSError:pass
            if generation.exists():skipped.append(str(generation))
        except (OSError,ValueError,KeyError,TypeError) as error:
            skipped.append(str(generation)+'：'+str(error))
    current=runtime/'current.json'
    if current.exists() and not current.is_symlink() and not current.is_junction():
        try:
            state=read_json(current);generation=state.get('generation','')
            if re.fullmatch('[a-f0-9]{32}',generation) and _owned_runtime(state,generation) and not (runtime/generation).exists():
                current.unlink();removed.append(str(current))
        except (OSError,ValueError,AttributeError):skipped.append(str(current))
    return removed,skipped


def _remove_file(root, relative, removed):
    path = checked_directory(root, relative)
    if path.is_symlink() or path.is_junction():
        raise ValueError('清理目标包含链接，已停止清理。')
    if path.is_file():
        path.unlink()
        removed.append(str(path))


def clean_known_data(root, *, caches=False, models=False, recovery=False):
    """Remove recognized files only; never recursively erase user directories.

    The caller must validate ownership, absence of pending migration and acquire
    both desktop and resource session locks before invoking this function.
    """
    root = Path(root)
    if root.is_symlink() or root.is_junction():
        raise ValueError('资源目录是链接，无法清理。')
    removed = []
    if caches:
        result = clear_image_cache(root)
        removed.extend(str(root / item) for item in result['removed'])
        _remove_file(root, 'errors.log', removed)
        _remove_file(root, 'worker-startup.log', removed)
        _remove_file(root, 'cache/active-project.json', removed)
    if models:
        from .model_catalog import MODELS
        from .native_runtime import catalog
        for spec in MODELS:
            name = spec['file']
            if Path(name).name != name:
                raise ValueError('模型文件清单无效。')
            for suffix in ('', '.part', '.part.json', '.part.invalid'):
                _remove_file(root, 'models/' + name + suffix, removed)
            _remove_file(root, 'models/' + Path(name).stem + '.download.json', removed)
        names = {wheel['filename'] for profile in catalog()['profiles'].values() for wheel in profile['wheels']}
        for name in names:
            if Path(name).name != name:
                raise ValueError('运行库文件清单无效。')
            for suffix in ('', '.part', '.part.json'):
                _remove_file(root, 'runtime/native-v1/downloads/' + name + suffix, removed)
    if recovery:
        _remove_file(root, 'recovery/untitled.geoforma.json', removed)
        _remove_file(root, 'recovery/untitled.geoforma.json.autosave', removed)
    return removed


def _local_data_root():
    import ctypes,sys
    if sys.platform!='win32':raise ValueError('当前系统不支持卸载清理。')
    path=ctypes.create_unicode_buffer(32768)
    if ctypes.windll.shell32.SHGetFolderPathW(None,0x001c,None,0,path)!=0 or not path.value:
        raise ValueError('无法确认当前用户的数据目录。')
    return Path(path.value)/'GeoForma'


def _has_remaining_content(root, data):
    """Never discard location history while unknown resources may need it."""
    if not root.exists():return False
    ignored={root/'.cache-session.lock',data/'.desktop.lock',root/'.geoforma-resources',
             data/'resource-location.json',data/'resource-migration-history.json',
             root/'runtime'/'native-v1'/'install.lock'}
    def fail(error):raise error
    try:
        for folder,dirs,files in os.walk(root,followlinks=False,onerror=fail):
            parent=Path(folder)
            for name in dirs:
                path=parent/name
                if path.is_symlink() or path.is_junction():return True
            for name in files:
                path=parent/name
                if path not in ignored:return True
    except OSError:return True
    return False


def cleanup_selected(mask, expected_root=None):
    """Apply a previously confirmed selection to this desktop user's data.

    Unknown files are retained. Raise on a busy session, untrusted identity,
    pending migration or invalid location.
    """
    from .uninstall_identity import current_user_owns_desktop
    if not current_user_owns_desktop():
        raise ValueError('无法确认当前账户与桌面用户一致，未清理任何数据。')
    if not isinstance(mask, int) or mask < 0 or mask > 15:
        raise ValueError('清理选项无效。')
    if mask & 11 and (not expected_root or not Path(expected_root).is_absolute()):
        raise ValueError('无法确认用户选择的资源目录，未清理任何数据。')
    from .session_guard import desktop_session, resource_session
    from .resource_location import require_resource_dir
    from PySide6.QtCore import QSettings
    data = _local_data_root()
    if data.is_symlink() or data.is_junction():
        raise ValueError('数据目录是链接，无法清理。')
    with desktop_session(data) as acquired:
        if not acquired:
            raise ValueError('GeoForma 正在使用数据，请关闭软件后重试。')
        journal=data/'resource-migration.json'
        if journal.exists() or journal.is_symlink() or journal.is_junction():
            raise ValueError('资源迁移尚未完成，请先完成迁移；未清理任何数据。')
        with resource_session():
            # The resource resolver supports a test/developer environment
            # override; a privileged uninstaller must never honor it.
            override=os.environ.pop('GEOFORMA_DATA_DIR',None)
            try:root = require_resource_dir(data) if mask & 11 else data
            finally:
                if override is not None:os.environ['GEOFORMA_DATA_DIR']=override
            # require_resource_dir acquires the resource lease. Compare only
            # after the lease is held, before deleting any selected data.
            if mask & 11 and os.path.normcase(str(Path(root).resolve())) != os.path.normcase(str(Path(expected_root).resolve())):
                raise ValueError('资源目录已更改，请重新确认后再清理；未清理任何数据。')
            removed = clean_known_data(root, caches=bool(mask & 1), models=bool(mask & 2), recovery=bool(mask & 8))
            skipped=[]
            if mask & 2:
                cleaned,skipped=clean_installed_runtimes(root);removed.extend(cleaned)
            if mask & 4:
                settings = QSettings('GeoForma','GeoForma')
                for key in settings.allKeys():
                    if not (mask & 8) and key.startswith('recovery/'):
                        continue
                    settings.remove(key)
                settings.sync()
                if settings.status() != settings.Status.NoError:
                    raise OSError('部分设置无法清理，请检查权限。')
            if mask==15:
                if skipped or _has_remaining_content(root,data) or (data!=root and _has_remaining_content(data,data)):
                    skipped.append('仍有数据保留，资源目录定位及迁移记录已保留。')
                else:
                    for name in ('resource-location.json','resource-migration-history.json'):
                        _remove_file(data,name,removed)
            return {'removed': removed, 'skipped': skipped, 'root': str(root)}
