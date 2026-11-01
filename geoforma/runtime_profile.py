"""Validated source-runtime overlay and release security floors; no model imports."""
import importlib.metadata
import os,sys
from pathlib import Path
from .atomic_io import read_json

SECURITY_MINIMUMS={'certifi':'2026.10.19','filelock':'4.2.1','Pillow':'13.0.0',
                   'setuptools':'84.1.0','torch':'2.13.0','torchvision':'0.28.0',
                   'hydra-core':'1.3.8','requests':'2.33.0','urllib3':'2.8.0','idna':'3.15'}


def activate_security_profile(root=None):
    if getattr(sys,'frozen',False):return False
    root=Path(root) if root else Path(__file__).resolve().parents[1]
    target=root/'environment'/'security-runtime';marker=target/'geoforma-profile.json'
    if not marker.is_file():return False
    profile=read_json(marker)
    if not isinstance(profile,dict) or profile.get('validated') is not True or profile.get('python')!=sys.implementation.cache_tag or profile.get('platform')!=sys.platform:
        raise RuntimeError('GeoForma 安全运行层尚未通过当前 Python/系统验证。')
    versions=profile.get('versions')
    if not isinstance(versions,dict) or any(not isinstance(name,str) or not isinstance(version,str) for name,version in versions.items()):raise RuntimeError('安全运行层缺少完整的依赖版本记录。')
    require_release_security(versions)
    if target.is_symlink() or target.is_junction() or marker.is_symlink() or not target.resolve().is_relative_to((root/'environment').resolve()):raise RuntimeError('安全运行层路径无效。')
    location=str(target.resolve());previous=list(sys.path)
    sys.path[:]=[location]+[value for value in sys.path if value!=location]
    try:
        for name,expected in versions.items():
            if importlib.metadata.version(name)!=expected:raise RuntimeError('安全运行层版本不一致：'+name)
    except Exception:
        sys.path[:]=previous
        raise
    inherited=[value for value in os.environ.get('PYTHONPATH','').split(os.pathsep) if value and value!=location]
    os.environ['PYTHONPATH']=os.pathsep.join([location,*inherited])
    return True


def release_security_issues(versions=None):
    from packaging.version import Version
    if versions is not None:versions={name.casefold().replace('_','-'):value for name,value in versions.items()}
    issues=[]
    for name,minimum in SECURITY_MINIMUMS.items():
        try:actual=versions.get(name.casefold().replace('_','-')) if versions is not None else importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:actual=None
        if actual is None or Version(actual)<Version(minimum):issues.append(f'{name}: {actual or "missing"} < {minimum}')
    return issues


def require_release_security(versions=None):
    issues=release_security_issues(versions)
    if issues:raise ValueError('发布环境尚含已知受影响依赖，请先升级并验证：\n'+'\n'.join(issues))
