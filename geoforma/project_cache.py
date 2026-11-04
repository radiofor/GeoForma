"""Disposable image caches belong to one active project, never to project JSON."""
from pathlib import Path
import re
import time
from uuid import uuid4
from .atomic_io import atomic_json,read_json

OWNER_PATTERN=re.compile(r'[a-f0-9]{32}|[a-f0-9]{64}')
FILE_PATTERN=re.compile(r'(?:[a-f0-9]{64}\.(?:pt|json)(?:\.tmp)?|[a-f0-9]{64}\.tmp|\.[a-f0-9]{64}\.(?:pt|json)\.[A-Za-z0-9_-]+\.tmp)')
TEMP_PATTERN=re.compile(r'(?:[a-f0-9]{64}\.(?:pt|json)\.tmp|[a-f0-9]{64}\.tmp|\.[a-f0-9]{64}\.(?:pt|json)\.[A-Za-z0-9_-]+\.tmp)')
TEMP_MAX_AGE=7*24*60*60


def checked_directory(root,relative):
    root=Path(root).resolve();target=root/relative
    # Check every component before following a reparse point or enumerating it.
    current=root
    for part in Path(relative).parts:
        current=current/part
        if current.is_symlink() or current.is_junction():raise ValueError('缓存目录包含链接，拒绝访问。')
    if not target.resolve().is_relative_to(root):raise ValueError('缓存目录超出用户数据目录。')
    return target


def clear_image_cache(root):
    root=Path(root).resolve();removed=[];size=0
    for relative in ('cache/features',):
        target=checked_directory(root,relative)
        if not target.exists():continue
        for path in target.iterdir():
            if FILE_PATTERN.fullmatch(path.name) and not path.is_symlink() and path.is_file():
                size+=path.stat().st_size;path.unlink();removed.append(str(path.relative_to(root)))
    exchange=checked_directory(root,'runtime/exchange')
    if exchange.exists():
        for worker in exchange.iterdir():
            if not re.fullmatch(r'worker_[A-Za-z0-9_-]+',worker.name) or worker.is_symlink() or worker.is_junction() or not worker.is_dir():continue
            for item in worker.iterdir():
                if item.is_symlink() or item.is_junction():continue
                files=[item] if item.name=='worker.log' and item.is_file() else list(item.iterdir()) if re.fullmatch('[a-f0-9]{32}',item.name) and item.is_dir() else []
                for path in files:
                    if path.name not in ('worker.log','input.npz','output.npz') or path.is_symlink() or not path.is_file():continue
                    size+=path.stat().st_size;path.unlink();removed.append(str(path.relative_to(root)))
                if item.is_dir() and not any(item.iterdir()):item.rmdir()
            if not any(worker.iterdir()):worker.rmdir()
    return dict(removed=removed,bytes=size,projects_preserved=True,models_preserved=True,recovery_preserved=True)


def prune_abandoned_cache_temps(root,now=None):
    """Only call after the old model writer stops; completed features stay intact."""
    root=Path(root).resolve();cutoff=(time.time() if now is None else now)-TEMP_MAX_AGE
    removed=[];size=0
    for relative in ('cache/features',):
        try:
            folder=checked_directory(root,relative)
            if not folder.is_dir():continue
            for path in folder.iterdir():
                try:
                    if not TEMP_PATTERN.fullmatch(path.name) or path.is_symlink() or path.is_junction() or not path.is_file():continue
                    info=path.stat()
                    if info.st_mtime>cutoff:continue
                    path.unlink();removed.append(str(path.relative_to(root)));size+=info.st_size
                except OSError:continue
        except (OSError,ValueError):continue
    return dict(removed=removed,bytes=size,projects_preserved=True,models_preserved=True,recovery_preserved=True)


def activate_project_cache(root,owner):
    if not isinstance(owner,str) or not OWNER_PATTERN.fullmatch(owner):raise ValueError('项目缓存标识无效。')
    root=Path(root).resolve();folder=checked_directory(root,'cache');folder.mkdir(parents=True,exist_ok=True)
    manifest=folder/'active-project.json'
    if manifest.is_symlink():raise ValueError('缓存归属文件不能为链接。')
    try:record=read_json(manifest);previous=record.get('owner');revision=record.get('revision')
    except (OSError,ValueError,AttributeError):previous=revision=None
    if previous==owner and isinstance(revision,str) and re.fullmatch('[a-f0-9]{32}',revision):
        return dict(prune_abandoned_cache_temps(root),cleared=False,revision=revision)
    result=clear_image_cache(root)
    # Publish ownership only after a successful complete cleanup, so retrying
    # after a sharing violation or interrupted cleanup cannot reuse stale state.
    revision=uuid4().hex
    atomic_json(manifest,{'schema':1,'owner':owner,'revision':revision})
    return dict(result,cleared=True,revision=revision)
