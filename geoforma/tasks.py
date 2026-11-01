import traceback
import threading
from PySide6.QtCore import QObject,QRunnable,Signal,Slot


class Cancelled(Exception):pass


class TaskSignals(QObject):
    progress=Signal(int,int,str)
    preview=Signal(object)
    result=Signal(object)
    error=Signal(str)
    finished=Signal()


class Task(QRunnable):
    def __init__(self,fn):
        super().__init__();self.fn=fn;self.signals=TaskSignals();self.cancel_event=threading.Event()

    def cancel(self):self.cancel_event.set()

    def check(self):
        if self.cancel_event.is_set():raise Cancelled('任务已取消；已完成缓存保留。')

    @Slot()
    def run(self):
        try:self.signals.result.emit(self.fn(self))
        except Cancelled as e:self.signals.error.emit(str(e))
        except Exception:self.signals.error.emit(traceback.format_exc())
        finally:
            self.fn=None
            self.signals.finished.emit()
