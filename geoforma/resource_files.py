"""Pinned resource I/O: resumable HTTPS, verified local copies, atomic publication."""
import hashlib,os,re,shutil,time
from pathlib import Path
from urllib.error import HTTPError,URLError
from urllib.request import Request
from .network import open_https
from .atomic_io import atomic_target
from .resource_lock import resource_lock as _lock

def report(task,text,current=0,total=0):
    task.check()
    stage=text.split(' · ')[0];now=time.monotonic();previous=getattr(task,'_resource_progress',None)
    if previous and stage==previous[0] and now-previous[1]<.05 and current!=total:return
    task._resource_progress=(stage,now)
    task.signals.progress.emit(min(99,int(100*current/total)) if total and current<total else 100 if total else 0,100 if total else 0,text)

def verify(path,spec,task):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size!=spec['bytes']:raise ValueError('文件大小不匹配：'+spec['filename'])
    digest=hashlib.sha256();done=0
    with path.open('rb') as stream:
        while block:=stream.read(4*1024**2):
            digest.update(block);done+=len(block);report(task,'校验 '+spec['filename'],done,spec['bytes'])
    if digest.hexdigest()!=spec['sha256']:raise ValueError('SHA256 校验失败：'+spec['filename'])
    task.check();return path

def _download(spec,part,task):
    offset=part.stat().st_size if part.exists() else 0
    if offset>=spec['bytes']:part.unlink();offset=0
    headers={'User-Agent':'GeoForma','Accept-Encoding':'identity'}
    if offset:headers['Range']=f'bytes={offset}-'
    report(task,'连接'+spec.get('source','官方源')+' · '+spec['filename'])
    with open_https(Request(spec['url'],headers=headers),timeout=20) as response:
        status=response.getcode()
        if status==206:
            match=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',response.headers.get('Content-Range',''))
            if not match or int(match[1])!=offset or int(match[3])!=spec['bytes']:raise ValueError('下载续传范围不匹配。')
        elif status==200:offset=0
        else:raise ValueError('下载响应异常。')
        if 'text/html' in response.headers.get('Content-Type','').lower():raise ValueError('下载地址返回了网页。')
        with part.open('ab' if offset else 'wb') as stream:
            done=offset
            while True:
                task.check();block=response.read(1024**2)
                if not block:break
                done+=len(block)
                if done>spec['bytes']:raise ValueError('下载文件超过固定大小。')
                stream.write(block);report(task,f"下载 {spec['name']} · {done/1024**2:.1f} / {spec['bytes']/1024**2:.1f} MiB",done,spec['bytes'])
            stream.flush();os.fsync(stream.fileno())
        if done!=spec['bytes']:raise OSError('下载未完成，已保留进度供重试续传。')

def acquire(spec,folder,task,source=None):
    """Only caller-owned, pinned catalog entries are accepted; no pip or scripts."""
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);target=folder/spec['filename']
    if target.name!=spec['filename'] or Path(spec['filename']).name!=spec['filename']:raise ValueError('资源文件名无效。')
    lock=target.with_suffix(target.suffix+'.lock');part=target.with_suffix(target.suffix+'.part')
    if any(p.is_symlink() or p.is_junction() for p in (folder,target,lock,part)):raise ValueError('资源路径不能为外部链接。')
    with _lock(lock,task):
        if source:
            source=verify(source,spec,task)
            if source.resolve()==target.resolve():return target
            with atomic_target(target) as part:
                done=0
                with source.open('rb') as src,part.open('wb') as dst:
                    while block:=src.read(4*1024**2):
                        task.check();dst.write(block);done+=len(block)
                        report(task,f"安装 · {spec['filename']} · {done/1024**2:.1f} / {spec['bytes']/1024**2:.1f} MiB",done,spec['bytes'])
                verify(part,spec,task)
        elif target.is_file():
            try:return verify(target,spec,task)
            except ValueError:target.unlink()
        if target.is_file():return target
        if shutil.disk_usage(folder).free<spec['bytes']+256*1024**2:raise OSError('资源下载目录的磁盘空间不足。')
        part=target.with_suffix(target.suffix+'.part')
        if part.is_symlink() or target.is_symlink():raise ValueError('资源路径不能为符号链接。')
        if part.is_file() and part.stat().st_size==spec['bytes']:
            try:verify(part,spec,task)
            except ValueError:part.unlink(missing_ok=True)
            else:task.check();os.replace(part,target);return target
        for attempt in range(3):
            try:_download(spec,part,task);break
            except (URLError,OSError) as error:
                if isinstance(error,HTTPError) and 400<=error.code<500 or attempt==2:raise RuntimeError('自动下载失败，可重试或使用本地文件导入。'+str(error)) from error
                for _ in range(10):task.check();time.sleep(.1)
        try:verify(part,spec,task)
        except ValueError:part.unlink(missing_ok=True);raise
        task.check();os.replace(part,target);return target
