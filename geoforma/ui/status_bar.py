"""Transient notifications share a fixed text slot instead of hiding other status items."""
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QStatusBar,QStackedWidget
from .status_visuals import StatusDetail


class WorkbenchStatusBar(QStatusBar):
    def __init__(self,task_text,parent=None):
        super().__init__(parent);self._message='';self._task_active=False;self._remaining=0
        self.text_slot=QStackedWidget();self.text_slot.setObjectName('statusMessageGroup');self.text_slot.setFixedHeight(34);self.content=None
        self.text_slot.setStyleSheet('QStackedWidget#statusMessageGroup{background:#f1f6fa;border:1px solid #d5e3ed;border-radius:7px;}')
        self.text_slot.addWidget(task_text)
        self.notice=StatusDetail(notice=True,wrap=True);self.text_slot.addWidget(self.notice)
        self.background=StatusDetail(wrap=True);self._background=''
        self._layout_timer=QTimer(self);self._layout_timer.setSingleShot(True);self._layout_timer.timeout.connect(self._fit_status)
        self.notice.textChanged.connect(self._schedule_fit);task_text.textChanged.connect(self._schedule_fit)
        self.message_timer=QTimer(self);self.message_timer.setSingleShot(True)
        self.message_timer.timeout.connect(self.clearMessage)
        self._notice_hovered=False;self.notice.hoverChanged.connect(self._notice_hover_changed)

    def showMessage(self,message,timeout=0):
        self.message_timer.stop();self._message=str(message);self.notice.setText(self._message)
        self._remaining=max(0,timeout) if self._message else 0
        self._select_message()
        if self._remaining and not self._task_active and not self._pause_notice():self.message_timer.start(self._remaining)
        self._schedule_fit()
        self.messageChanged.emit(self._message)

    def clearMessage(self):
        self.showMessage('')

    def report_error(self,message,source=None,parent=None):
        from .error_toast import ErrorToast
        if parent is not None:
            if not hasattr(parent,'_error_toast'):parent._error_toast=ErrorToast(parent,None)
            parent._error_toast.show(message,source)
        else:
            if not hasattr(self,'_error_toast'):self._error_toast=ErrorToast(self.window(),self)
            self._error_toast.show(message,source)

    def reset_error_source(self,source):
        if hasattr(self,'_error_toast'):self._error_toast.reset_source(source)

    def clear_error_source(self,source):
        if hasattr(self,'_error_toast'):self._error_toast.clear_source(source)

    def currentMessage(self):return self._message

    def set_task_active(self,active):
        active=bool(active)
        if active and not self._task_active and self.message_timer.isActive():
            self._remaining=max(1,self.message_timer.remainingTime());self.message_timer.stop()
        elif not active and self._task_active and self._message and self._remaining and not self._pause_notice():
            self.message_timer.start(self._remaining)
        self._task_active=active
        self._select_message()

    def set_content(self,content,context=None,progress=None):
        # Own the row geometry instead of inheriting native status-layout margins.
        self.content=content;content.setParent(self);content.setGeometry(0,1,self.width(),self.height()-1);content.show()
        self.context=context;self.progress_panel=progress
        if context:
            self.text_slot.addWidget(context);context.textChanged.connect(self._select_message)
        self.text_slot.addWidget(self.background);self.background.textChanged.connect(self._schedule_fit)
        self._select_message()

    def set_background_message(self,message):
        self._background=str(message or '');self.background.setText(self._background);self._select_message()

    def _select_message(self):
        index=0 if self._task_active else 1 if self._message else self.text_slot.indexOf(self.background) if self._background else 2 if getattr(self,'context',None) else 0
        self.text_slot.setCurrentIndex(index);self._schedule_fit()

    def _pause_notice(self):
        return self._notice_hovered and self.notice.scrollbar.maximum()>0

    def _notice_hover_changed(self,hovered):
        if hovered==self._notice_hovered:return
        self._notice_hovered=hovered
        if self._pause_notice() and self.message_timer.isActive():
            self._remaining=max(1,self.message_timer.remainingTime());self.message_timer.stop()
        elif not hovered and self._message and self._remaining and not self._task_active:
            self.message_timer.start(self._remaining)

    def _schedule_fit(self):
        if not self._layout_timer.isActive():self._layout_timer.start(0)

    def _fit_status(self):
        if not self.content:return
        self.content.layout().activate()
        active=self.text_slot.currentWidget()
        lines=active.line_count() if active and active.wrap else 1
        line_height=active.fontMetrics().height() if active else self.fontMetrics().height()
        height=max(42,22+min(4,lines)*line_height)
        if self.height()!=height:self.setFixedHeight(height)
        detail_height=height-8
        self.text_slot.setFixedHeight(detail_height)
        if self.progress_panel:self.progress_panel.setFixedHeight(detail_height)
        for detail in (self.text_slot.widget(0),self.notice,getattr(self,'context',None),self.background):
            if detail:detail.setFixedHeight(detail_height)
        self.content.setGeometry(0,1,self.width(),height-1)
        self.content.layout().activate()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if self.content:self.content.setGeometry(0,1,self.width(),self.height()-1)
        self._schedule_fit()
