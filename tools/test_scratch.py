"""Own and retire isolated pytest scratch directories without touching reports."""
import os,re,shutil,time,uuid
from pathlib import Path
from geoforma.project_cache import checked_directory
from geoforma.resource_lock import try_resource_lock

MARKER='GeoForma pytest scratch v1\n'
MAX_AGE=7*86400


def remove_checked(root,target):
    root=Path(root).resolve();target=Path(target)
    if target.is_symlink() or target.is_junction():raise ValueError('清理目标不能是链接。')
    resolved=target.resolve()
    if resolved==root or not resolved.is_relative_to(root):raise ValueError('清理目标超出范围。')
    def fail(error):raise error
    for directory,children,files in os.walk(target,followlinks=False,onerror=fail):
        for name in children+files:
            path=Path(directory)/name
            if path.is_symlink() or path.is_junction():raise ValueError('清理目录包含链接。')
    shutil.rmtree(target)


def scratch_root(root):
    root=Path(root).resolve();folder=checked_directory(root,'build/test-runs')
    folder.mkdir(parents=True,exist_ok=True)
    return folder


def prune_stale(root,now=None):
    folder=scratch_root(root);now=time.time() if now is None else now;removed=[]
    for path in folder.iterdir():
        if not re.fullmatch(r'run-[a-f0-9]{32}',path.name) or path.is_symlink() or path.is_junction() or not path.is_dir():continue
        try:
            marker=path/'.geoforma-owned'
            if marker.is_symlink() or not marker.is_file() or marker.read_text(encoding='utf-8')!=MARKER or marker.stat().st_mtime>now-MAX_AGE:continue
            lock=path/'.active.lock'
            if lock.is_symlink() or not lock.is_file():continue
            with try_resource_lock(lock) as acquired:
                if not acquired:continue
            remove_checked(folder,path);removed.append(path.name)
        except (OSError,ValueError):continue
    return removed


def create_scratch(root):
    folder=scratch_root(root)
    path=folder/('run-'+uuid.uuid4().hex);path.mkdir()
    (path/'.geoforma-owned').write_text(MARKER,encoding='utf-8')
    return path
