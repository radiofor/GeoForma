"""Shared native initialization for the desktop and spawn entry points; no Qt."""
import os
import sys

_worker_log=None


def worker_startup_stage(stage):
    if _worker_log is None:return
    try:
        from .logging_limits import MAX_LOG_BYTES
        if _worker_log.tell() > MAX_LOG_BYTES:
            _worker_log.seek(0);_worker_log.truncate()
        from datetime import datetime
        _worker_log.write(f'{datetime.now().isoformat(timespec="seconds")} [{os.getpid()}] {str(stage)[-MAX_LOG_BYTES//4:]}\n')
    except (OSError,ValueError):pass


def configure_worker_diagnostics():
    global _worker_log
    if _worker_log is not None:return
    if not getattr(sys,'frozen',False) or '--multiprocessing-fork' not in sys.argv:return
    try:
        from .resource_location import require_resource_dir
        path=require_resource_dir()/'worker-startup.log'
        if path.is_symlink() or path.is_junction():return
        stream=path.open('a',encoding='utf-8',buffering=1)
        _worker_log=stream
        sys.stderr=stream
        if sys.stdout is None:sys.stdout=stream
        worker_startup_stage(f'Python worker entry; executable={sys.executable}; bundle={getattr(sys,"_MEIPASS","")}')
        import faulthandler
        faulthandler.enable(file=stream)
    except (OSError,ValueError,RuntimeError):pass


def configure_native_environment():
    """Run inside every Python process before adding optional inference DLLs.

    Frozen spawn children bypass main(), so initialization must not depend on
    the desktop entry point. Load bundled Pillow codecs before TorchVision.
    """
    from .runtime_profile import activate_security_profile
    activate_security_profile()
    os.environ['GDAL_VRT_ENABLE_PYTHON']='NO'
    from environment._geoforma_runtime import configure
    configure()
    from PIL import Image
