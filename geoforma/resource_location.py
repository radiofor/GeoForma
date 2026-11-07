"""Persistent resource location, independent of project and recovery data."""
from pathlib import Path
import os
from .atomic_io import atomic_json,read_json
from .domain import data_dir

FOLDER='GeoForma-Resources'
CONFIG='resource-location.json'
MARKER='.geoforma-resources'
MARKER_CONTENT='GeoForma resource directory v1\n'


def valid_resource_marker(marker):
    """Check the fixed marker without reading an arbitrarily large file."""
    marker=Path(marker)
    if marker.is_symlink() or marker.is_junction() or not marker.is_file():return False
    expected=MARKER_CONTENT.encode('utf-8')
    with marker.open('rb') as stream:data=stream.read(len(expected)+2)
    return data.replace(b'\r\n',b'\n').replace(b'\r',b'\n')==expected


def default_resource_dir(root):
    """Keep established user resources; new profiles get a separate folder."""
    root=Path(root)
    if os.environ.get('GEOFORMA_DATA_DIR'):return root
    if (root/'cache'/'active-project.json').is_file() or (root/'runtime'/'native-v1'/'current.json').is_file():return root
    for cache_name in ('features',):
        folder=root/'cache'/cache_name
        if folder.is_dir() and any(p.is_file() and p.suffix.lower() in ('.pt','.json') for p in folder.iterdir()):return root
    models=root/'models'
    if models.is_dir() and any(p.is_file() and p.suffix.lower() in ('.pt','.pth','.part') for p in models.iterdir()):return root
    downloads=root/'runtime'/'native-v1'/'downloads'
    if downloads.is_dir() and any(p.is_file() and '.whl' in p.name.lower() for p in downloads.iterdir()):return root
    return root.parent/FOLDER


def current_resource_dir(default=None):
    root=Path(default) if default is not None else data_dir()
    config=root/CONFIG
    if not config.is_file():return default_resource_dir(root)
    value=read_json(config,max_bytes=16384)
    if not isinstance(value,dict) or value.get('kind')!='geoforma-resource-location-v1' or not isinstance(value.get('path'),str):
        raise ValueError('资源目录配置无效，请检查数据目录中的配置文件。')
    path=Path(value['path'])
    if not path.is_absolute() or (path.name.casefold()!=FOLDER.casefold() and path.resolve()!=root.resolve()):raise ValueError('资源目录配置路径无效。')
    return path


def require_resource_dir(default=None):
    root=Path(default) if default is not None else data_dir()
    journal=root/'resource-migration.json'
    if journal.exists() or journal.is_symlink() or journal.is_junction():raise ValueError('资源迁移尚未完成，请先继续迁移。')
    path=current_resource_dir(root)
    from .session_guard import guard_resource
    if path==root:
        guard_resource(path)
        return path
    if not (root/CONFIG).is_file() and path==default_resource_dir(root):
        if path.is_symlink() or path.is_junction():raise ValueError('资源目录不能是链接。')
        path.mkdir(parents=True,exist_ok=True)
        marker=path/MARKER
        if not marker.exists():
            if any(path.iterdir()):raise ValueError('默认资源目录已有其他文件，请选择其他目录。')
            with marker.open('x',encoding='utf-8',newline='\n') as stream:stream.write(MARKER_CONTENT)
    marker=path/MARKER
    if path.is_symlink() or path.is_junction() or not valid_resource_marker(marker):
        raise ValueError('资源目录不可访问或归属标记无效，请检查所选磁盘。')
    guard_resource(path)
    return path


def prepare_resource_parent(parent):
    parent=Path(parent).expanduser()
    if not parent.is_absolute() or not parent.is_dir():raise ValueError('请选择已存在的绝对目录。')
    if parent.is_symlink() or parent.is_junction():raise ValueError('资源目录不能选择链接。')
    path=parent if parent.name.casefold()==FOLDER.casefold() else parent/FOLDER
    if path.is_symlink() or path.is_junction():raise ValueError('资源目录不能是链接。')
    path.mkdir(parents=True,exist_ok=True)
    marker=path/MARKER
    if marker.is_symlink() or marker.is_junction():raise ValueError('资源目录标记不能是链接。')
    if marker.is_file():
        if not valid_resource_marker(marker):raise ValueError('资源目录归属标记无效。')
    elif any(path.iterdir()):raise ValueError('该 GeoForma-Resources 文件夹已有其他文件，请选择其他目录。')
    else:
        with marker.open('x',encoding='utf-8',newline='\n') as stream:stream.write(MARKER_CONTENT)
    return path.resolve()


def set_resource_parent(parent):
    path=prepare_resource_parent(parent)
    atomic_json(data_dir()/CONFIG,{'kind':'geoforma-resource-location-v1','path':str(path)},indent=2)
    return path


def reset_resource_dir():
    root=data_dir();config=root/CONFIG
    if config.is_symlink() or config.is_junction():raise ValueError('资源目录配置不能是链接。')
    config.unlink(missing_ok=True)
    return default_resource_dir(root)
