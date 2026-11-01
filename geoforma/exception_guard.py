"""Prevent Qt event errors from recursively opening error dialogs."""
import threading
import time
import traceback
from collections import OrderedDict


def guarded_exception_hook(log_error, show_error, *, clock=time.monotonic, cooldown=5.0):
    """Suppress recursive dialogs and throttle continuously recurring errors."""
    lock=threading.RLock()
    showing=False
    recent=OrderedDict()

    def hook(kind,value,tb):
        nonlocal showing
        signature=(kind,str(value))
        now=clock()
        with lock:
            previous=recent.pop(signature,None)
            recent[signature]=now
            if len(recent)>128:recent.popitem(last=False)
            if previous is not None and now-previous<cooldown:return
            display=not showing
            if display:showing=True
        try:
            try:log_error(''.join(traceback.format_exception(kind,value,tb)))
            except Exception:pass
            if display:
                try:show_error(value)
                except Exception:pass
        finally:
            if display:
                with lock:showing=False
    return hook
