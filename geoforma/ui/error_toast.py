"""Non-modal, short-lived error feedback for the main window."""
from PySide6.QtCore import Qt,QEvent,QObject,QTimer
from PySide6.QtWidgets import QLabel


class ErrorToast(QObject):
    def __init__(self,window,status_bar):
        super().__init__(window);self.window=window;self.status_bar=status_bar;self.source=None;self.last_key=None
        self.label=QLabel(window);self.label.setObjectName('errorToast');self.label.setTextFormat(Qt.TextFormat.PlainText);self.label.setWordWrap(True)
        self.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.label.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.label.setStyleSheet('QLabel#errorToast{background:#fff2f1;color:#9f3441;border:1px solid #e8b8bd;border-radius:7px;padding:10px 14px;}')
        self.message='';self.pending=[];self.label.hide();self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self._advance)
        window.installEventFilter(self)

    def show(self,message,source=None):
        text=str(message).strip()
        if not text:return
        key=(source,text)
        if self.label.isVisible():
            if self.last_key==key or key in self.pending:return
            if len(self.pending)>=4:self.pending.pop(0)
            self.pending.append(key);return
        self._display(key)

    def _display(self,key):
        source,text=key
        self.last_key=key;self.source=source;self.message=text;self.label.setText(text);self.label.ensurePolished();self.label.show();self._place();self.label.raise_();self.timer.start(2000)

    def _advance(self):
        self.label.hide();self.source=None;self.last_key=None
        if self.pending:self._display(self.pending.pop(0))

    def reset_source(self,source):
        if self.last_key is not None and self.last_key[0]==source:self.last_key=None
        self.pending=[key for key in self.pending if key[0]!=source]

    def clear_source(self,source):
        self.reset_source(source)
        if self.source==source:self.timer.stop();self._advance()

    def _place(self):
        width=min(520,max(1,self.window.width()-32));self.label.setFixedWidth(width)
        bottom=self.status_bar.mapTo(self.window,self.status_bar.rect().topLeft()).y() if self.status_bar else self.window.height();limit=max(42,bottom-20)
        self.label.setText(self.message);height=self.label.heightForWidth(width)
        if height>limit:
            suffix='…（详见任务记录）';low=0;high=len(self.message)
            while low<high:
                middle=(low+high+1)//2;self.label.setText(self.message[:middle]+suffix)
                if self.label.heightForWidth(width)<=limit:low=middle
                else:high=middle-1
            self.label.setText(self.message[:low]+suffix);height=self.label.heightForWidth(width)
        self.label.setFixedHeight(min(limit,max(42,height)))
        self.label.move(max(0,self.window.width()-width-16),max(0,bottom-self.label.height()-10))

    def eventFilter(self,obj,event):
        # Qt can deliver events while the Python wrapper is being initialized
        # or after its widget children have already been destroyed.
        from shiboken6 import isValid
        window=getattr(self,'window',None);label=getattr(self,'label',None);status=getattr(self,'status_bar',None)
        if window is not None and obj is window and label is not None and isValid(window) and isValid(label):
            if event.type()==QEvent.Type.Resize and label.isVisible() and (status is None or isValid(status)):self._place()
        return False
