"""Transient notifications share a fixed text slot instead of hiding other status items."""
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QStatusBar,QStackedWidget
from .status_visuals import StatusDetail


class WorkbenchStatusBar(QStatusBar):
    def __init__(self,task_text,parent=None):
        super().__init__(parent);self._message='';self._task_active=False;self._remaining=0
        self.text_slot=QStackedWidget();self.text_slot.setFixedHeight(26);self.content=None
        self.text_slot.addWidget(task_text)
        self.notice=StatusDetail(notice=True);self.text_slot.addWidget(self.notice)
        self.message_timer=QTimer(self);self.message_timer.setSingleShot(True)
        self.message_timer.timeout.connect(self.clearMessage)

    def showMessage(self,message,timeout=0):
        self.message_timer.stop();self._message=str(message);self.notice.setText(self._message)
        self._remaining=max(0,timeout) if self._message else 0
        self.text_slot.setCurrentIndex(1 if self._message and not self._task_active else 0)
        if self._remaining and not self._task_active:self.message_timer.start(self._remaining)
        self.messageChanged.emit(self._message)

    def clearMessage(self):
        self.showMessage('')

    def currentMessage(self):return self._message

    def set_task_active(self,active):
        active=bool(active)
        if active and not self._task_active and self.message_timer.isActive():
            self._remaining=max(1,self.message_timer.remainingTime());self.message_timer.stop()
        elif not active and self._task_active and self._message and self._remaining:
            self.message_timer.start(self._remaining)
        self._task_active=active
        self.text_slot.setCurrentIndex(1 if self._message and not self._task_active else 0)

    def set_content(self,content):
        # Own the row geometry instead of inheriting native status-layout margins.
        self.content=content;content.setParent(self);content.setGeometry(0,1,self.width(),self.height()-1);content.show()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if self.content:self.content.setGeometry(0,1,self.width(),self.height()-1)
