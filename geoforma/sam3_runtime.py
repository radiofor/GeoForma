"""Locate the unmodified official SAM 3 package and its isolated dependencies."""
import sys
from .distribution import resource_root


def resource_compatibility():
    # Official SAM 3 uses this single resource API removed in modern setuptools.
    # Keep its code unchanged without downgrading the application's setuptools.
    from importlib.util import find_spec
    if 'pkg_resources' not in sys.modules and find_spec('pkg_resources') is None:
        from types import ModuleType
        from importlib.resources import files
        module=ModuleType('pkg_resources')
        module.resource_filename=lambda package,name:str(files(package).joinpath(name))
        sys.modules['pkg_resources']=module


def activate():
    root=resource_root()
    for path in (root/'sam3-runtime',root/'environment'/'sam3-runtime'):
        if (path/'sam3'/'__init__.py').is_file():
            value=str(path)
            if value not in sys.path:sys.path.insert(0,value)
            resource_compatibility()
            return path
    from importlib.util import find_spec
    if find_spec('sam3') is None:
        raise RuntimeError('SAM 3 官方代码或依赖缺失，请运行 environment/prepare_sam3.py 配置。')
    resource_compatibility()
    return None


def available():
    root=resource_root()
    return any((path/'sam3'/'__init__.py').is_file() for path in (root/'sam3-runtime',root/'environment'/'sam3-runtime'))
