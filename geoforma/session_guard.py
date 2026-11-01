"""Protect the single active project-cache owner in a user data directory."""
from contextlib import contextmanager
from pathlib import Path
import threading
from .resource_lock import try_resource_lock


@contextmanager
def desktop_session(root):
    root=Path(root).resolve();root.mkdir(parents=True,exist_ok=True)
    with try_resource_lock(root/'.desktop.lock') as acquired:
        yield acquired


_resource_lease=None


class ResourceLease:
    """Hold the cache root lock for the entire desktop or CLI operation."""
    def __init__(self):
        self.root=None;self._context=None;self._mutex=threading.RLock()

    @staticmethod
    def _path(root):return Path(root).resolve()

    def _take(self,root):
        root=self._path(root)
        context=try_resource_lock(root/'.cache-session.lock')
        if not context.__enter__():
            context.__exit__(None,None,None)
            raise ValueError('资源目录正在被另一个 GeoForma 会话使用。')
        return root,context

    def ensure(self,root):
        root=self._path(root)
        with self._mutex:
            if self.root==root:return
            if self.root is not None:raise ValueError('资源目录已更改，请在资源配置中重新选择目录。')
            self.root,self._context=self._take(root)

    @contextmanager
    def transition(self,root):
        """Reserve the new root until the caller has saved its settings."""
        root=self._path(root)
        with self._mutex:
            if self.root==root:
                yield
                return
            new_root,new_context=self._take(root)
            try:
                yield
            except BaseException:
                new_context.__exit__(None,None,None)
                raise
            old=self._context
            self.root,self._context=new_root,new_context
            if old:old.__exit__(None,None,None)

    def close(self):
        with self._mutex:
            if self._context:self._context.__exit__(None,None,None)
            self._context=None;self.root=None


def guard_resource(root):
    if _resource_lease is not None:_resource_lease.ensure(root)


@contextmanager
def resource_session():
    global _resource_lease
    if _resource_lease is not None:raise RuntimeError('资源会话已启动。')
    lease=ResourceLease();_resource_lease=lease
    try:yield lease
    finally:
        _resource_lease=None;lease.close()


def active_resource_lease():return _resource_lease
