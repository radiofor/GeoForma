"""Cancellable interprocess locks for app-owned downloads and installation."""
from contextlib import contextmanager
import sys,time


@contextmanager
def try_resource_lock(path):
    """Take an existing resource lock without waiting for an active operation."""
    if path.is_symlink() or path.is_junction():raise ValueError('资源锁不能指向外部链接。')
    stream=path.open('a+b');acquired=False
    try:
        if path.stat().st_size==0:stream.write(b'0');stream.flush()
        stream.seek(0)
        try:
            if sys.platform=='win32':
                import msvcrt
                msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            acquired=True
        except OSError:pass
        yield acquired
    finally:
        if acquired:
            stream.seek(0)
            if sys.platform=='win32':
                import msvcrt
                msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(),fcntl.LOCK_UN)
        stream.close()

@contextmanager
def resource_lock(path,task):
    if path.is_symlink() or path.is_junction():raise ValueError('资源锁不能指向外部链接。')
    stream=path.open('a+b')
    if path.stat().st_size==0:stream.write(b'0');stream.flush()
    acquired=False
    try:
        while not acquired:
            task.check();stream.seek(0)
            try:
                if sys.platform=='win32':
                    import msvcrt
                    msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                acquired=True
            except OSError:
                task.signals.progress.emit(0,0,'其他 GeoForma 进程正在配置此资源，等待完成…');time.sleep(.2)
        yield
    finally:
        if acquired:
            stream.seek(0)
            if sys.platform=='win32':
                import msvcrt
                msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(),fcntl.LOCK_UN)
        stream.close()
