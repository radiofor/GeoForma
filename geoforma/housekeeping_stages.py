"""Recognize and retire only abandoned, explicitly marked runtime stages."""
import os
import re
import time
from pathlib import Path
from .atomic_io import read_json
from .project_cache import checked_directory
from .resource_lock import try_resource_lock

STAGE_AGE=7*24*60*60
GENERATION=re.compile(r'[a-f0-9]{32}')


def installed_wheels(runtime):
    """Return wheels backed by an installed configuration under this data root."""
    from .native_runtime import _installed_state
    names=set();runtime=Path(runtime)
    try:
        for folder in runtime.iterdir():
            if not GENERATION.fullmatch(folder.name) or folder.is_symlink() or folder.is_junction() or not folder.is_dir():continue
            marker=folder/'installed.json'
            if marker.is_symlink() or marker.is_junction() or not marker.is_file():continue
            try:
                state=_installed_state(read_json(marker),runtime)
                if state and state['generation']==folder.name:names.update(row['filename'] for row in state['wheels'])
            except (OSError,ValueError,KeyError,TypeError):continue
    except OSError:pass
    return names


def _stage_files(stage,task):
    from .native_runtime import STAGE_MARKER
    allowed={'torch','torchvision','functorch','torchgen',STAGE_MARKER}
    for item in stage.iterdir():
        if item.name not in allowed and not re.fullmatch(r'[A-Za-z0-9_.+\-]+\.dist-info',item.name) and not re.fullmatch(r'\.installed\.json\.[a-z0-9_]{8}\.tmp',item.name):
            raise ValueError('运行库临时目录包含未知文件。')
    files=[];directories=[];size=0
    def fail(error):raise error
    for folder,children,names in os.walk(stage,topdown=True,followlinks=False,onerror=fail):
        task.check()
        for name in children+names:
            path=Path(folder)/name
            if path.is_symlink() or path.is_junction():raise ValueError('运行库临时目录包含链接。')
        for name in names:
            path=Path(folder)/name
            if not path.is_file():raise ValueError('运行库临时目录包含特殊文件。')
            size+=path.stat().st_size;files.append(path)
        directories.extend(Path(folder)/name for name in children)
    directories.sort(key=lambda path:len(path.parts),reverse=True)
    return files,directories,size


def clean_abandoned_stages(root,task,*,apply=False,now=None):
    """Protect current, installed, unmarked, linked and actively installing data."""
    from .native_runtime import STAGE_MARKER,STAGE_MARKER_CONTENT
    root=Path(root).resolve();cutoff=(time.time() if now is None else now)-STAGE_AGE
    report={'directories':[],'bytes':0,'skipped':[]}
    try:runtime=checked_directory(root,'runtime/native-v1')
    except (OSError,ValueError):return report
    if not runtime.is_dir():return report
    def scan():
        marker=runtime/'current.json';current=None
        try:
            if marker.is_symlink() or marker.is_junction():raise ValueError('当前运行库记录是链接。')
            if marker.exists():
                current=read_json(marker)['generation']
                if not isinstance(current,str) or not GENERATION.fullmatch(current):raise ValueError('当前运行库记录无效。')
        except (OSError,ValueError,TypeError,KeyError):
            report['skipped'].append('runtime/native-v1/current.json');return
        for stage in runtime.iterdir():
            task.check()
            try:
                if not GENERATION.fullmatch(stage.name) or stage.name==current or stage.is_symlink() or stage.is_junction() or not stage.is_dir():continue
                installed=stage/'installed.json';owner=stage/STAGE_MARKER
                if installed.exists() or installed.is_symlink() or installed.is_junction():continue
                if owner.is_symlink() or owner.is_junction() or not owner.is_file() or owner.stat().st_size>256 or owner.stat().st_mtime>cutoff:continue
                if owner.read_text(encoding='utf-8')!=STAGE_MARKER_CONTENT:continue
                if not stage.resolve().is_relative_to(runtime.resolve()) or stage.resolve()==runtime.resolve():raise ValueError('运行库临时目录越界。')
                files,folders,size=_stage_files(stage,task)
                if apply:
                    # Keep the ownership marker until the last file is removed,
                    # so a cancelled or interrupted cleanup remains retryable.
                    for path in files:
                        if path==owner:continue
                        task.check()
                        if path.is_symlink() or path.is_junction():raise ValueError('运行库临时目录包含链接。')
                        path.unlink()
                    for folder in folders:
                        task.check()
                        if folder.is_symlink() or folder.is_junction():raise ValueError('运行库临时目录包含链接。')
                        folder.rmdir()
                    task.check();owner.unlink();stage.rmdir()
                report['directories'].append(stage.relative_to(root).as_posix());report['bytes']+=size
            except (OSError,ValueError,UnicodeError):report['skipped'].append(stage.relative_to(root).as_posix())
    try:
        if apply:
            with try_resource_lock(runtime/'install.lock') as acquired:
                if acquired:scan()
        else:scan()
    except (OSError,ValueError):report['skipped'].append('runtime/native-v1')
    return report
