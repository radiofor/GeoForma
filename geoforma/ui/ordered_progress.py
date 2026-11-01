"""Give each imported file one display frame without sleeping in a worker."""
from collections import deque
from PySide6.QtCore import QObject,QTimer,Qt


class OrderedProgressDelivery(QObject):
    def __init__(self,parent,task,progress,result,error,finished):
        super().__init__(parent)
        self.task=task;self.callbacks=(progress,result,error,finished);self.pending=deque()
        self.timer=QTimer(self);self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(16);self.timer.timeout.connect(self.advance)

    def enqueue(self,kind,*args):
        # No display backlog means there is nothing to pace. In particular,
        # retain synchronous completion for operations with no file reports.
        if kind!=0 and not self.pending:
            self.callbacks[kind](*args)
            if kind==3:self.timer.stop();self.deleteLater()
            return
        self.pending.append((kind,args))
        if not self.timer.isActive():self.timer.start()

    def progress(self,current,total,text):self.enqueue(0,current,total,text)
    def result(self,value):self.enqueue(1,value)

    def error(self,message):
        self.pending.clear();self.enqueue(2,message)

    def finished(self):self.enqueue(3)

    def advance(self):
        painted=False
        while self.pending:
            kind,args=self.pending[0]
            cancelled=self.task.cancel_event.is_set()
            if kind==0 and cancelled:self.pending.popleft();continue
            if kind==0 and painted:break
            self.pending.popleft();self.callbacks[kind](*args)
            if kind==0:painted=True
            if kind==3:
                self.timer.stop();self.deleteLater();return
        if not self.pending:self.timer.stop()
