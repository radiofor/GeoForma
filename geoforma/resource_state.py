"""Cheap readiness snapshots shared by reminders, settings, and inference gates."""
from pathlib import Path
from stat import S_ISREG
from .model_catalog import MODELS,model_spec
from .weights import default_checkpoint
from . import native_runtime


def inspect_checkpoint(spec,path):
    """One lightweight file-status rule for model settings and resource setup."""
    try:
        path=Path(path)
        try:info=path.stat();size=info.st_size if S_ISREG(info.st_mode) else None
        except (FileNotFoundError,NotADirectoryError):size=None
        availability='missing' if size is None else 'configured' if path.name==spec['file'] and size==spec['bytes'] else 'local' if path.name!=spec['file'] and size>0 else 'incomplete'
    except (OSError,ValueError) as error:
        return dict(ready=False,availability='unavailable',path=str(path),spec=spec,error=str(error))
    return dict(ready=availability in ('configured','local'),availability=availability,path=str(path),spec=spec)


def checkpoint_state(config):
    spec=model_spec(config['variant'],config.get('backend','sam'))
    path=config.get('checkpoint') or spec['file']
    try:
        path=Path(config.get('checkpoint') or default_checkpoint(spec['variant'],spec['backend']))
        if path.name in {item['file'] for item in MODELS} and path.name!=spec['file']:path=default_checkpoint(spec['variant'],spec['backend'])
        if not path.is_file():path=default_checkpoint(spec['variant'],spec['backend'])
    except (OSError,ValueError) as error:
        return dict(ready=False,availability='unavailable',path=str(path),spec=spec,error=str(error))
    return inspect_checkpoint(spec,path)

def snapshot(config):
    runtime=native_runtime.status();weight=checkpoint_state(config)
    return dict(ready=runtime['ready'] and weight['ready'],runtime=runtime,weight=weight)


def inventory(config):
    """Settings-only inventory: small manifests and file metadata, no Torch/hashes.

    Unlike the inference gate, this includes installed but inactive CPU/GPU
    configurations and every model. Call on open/completion, not every UI tick.
    """
    active=native_runtime.status();installed=native_runtime.installed_runtimes()
    profiles={}
    for key,spec in native_runtime.catalog()['profiles'].items():
        wheel=next(item for item in spec['wheels'] if item['name']=='torch')
        profiles[key]=dict(key=key,title=spec['title'],version=wheel['version'],
            configured=any(state['profile']==key for state in installed) or bool(active['ready'] and active.get('profile')==key),current=active.get('profile')==key,
            bytes=sum(item['bytes'] for item in native_runtime.download_wheels(key)))
    version='';active_key=active.get('profile')
    if active.get('source')=='bundled':
        from importlib.metadata import version as package_version,PackageNotFoundError
        try:version=package_version('torch')
        except PackageNotFoundError:pass
        active_key=next((key for key,item in profiles.items() if item['version']==version),None)
        if active_key:profiles[active_key].update(configured=True,current=True)
    elif active_key in profiles:version=profiles[active_key]['version']
    models={}
    current_spec=model_spec(config['variant'],config.get('backend','sam'))
    for spec in MODELS:
        current=spec['id']==current_spec['id']
        state=checkpoint_state(config if current else dict(backend=spec['backend'],variant=spec['variant']))
        models[spec['id']]=state|{'current':current}
    return dict(runtime=active|{'version':version,'active_profile':active_key},profiles=profiles,models=models,current_model=current_spec)
