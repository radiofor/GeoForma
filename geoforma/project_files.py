"""Project file names and dialog filters, independent of JSON serialization."""
from pathlib import Path

PROJECT_SUFFIX='.gfm'
RECOVERY_NAME='untitled.gfm'
SAVE_FILTER='GeoForma 项目 (*.gfm)'
OPEN_FILTER=SAVE_FILTER


def project_name(path):
    name=Path(path).name
    return name[:-len(PROJECT_SUFFIX)] if name.lower().endswith(PROJECT_SUFFIX) else name


def new_project_path(path):
    path=Path(path);name=path.name
    if name.lower().endswith(PROJECT_SUFFIX):return path
    return path.with_name(name+PROJECT_SUFFIX)


def require_project_path(path):
    path=Path(path)
    if path.suffix.lower()!=PROJECT_SUFFIX:raise ValueError('项目文件必须使用 .gfm 后缀。')
    return path
