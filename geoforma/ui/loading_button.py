"""Small retained spinner inside a button; never changes its layout geometry."""
from PySide6.QtCore import Qt,QRectF,QTimer
from PySide6.QtGui import QColor,QPen,QPalette
from PySide6.QtWidgets import QPushButton,QStyleOptionButton,QStylePainter,QStyle


class LoadingButton(QPushButton):
    def __init__(self,text,parent=None):
        super().__init__(text,parent);self.busy=False;self.angle=0;self._idle_tooltip=''
        self.timer=QTimer(self);self.timer.setInterval(50);self.timer.timeout.connect(self.advance)

    def bind_progress(self,model,kind):
        def sync(state):
            active=state.phase=='running' and state.kind==kind and not getattr(self.window(),'closing',False)
            self.set_busy(active)
            if active:self.setToolTip(state.stage or state.title);self.setAccessibleName(state.title)
        model.changed.connect(sync);sync(model.state)

    def set_busy(self,busy):
        if self.busy==bool(busy):return
        self.busy=bool(busy)
        if self.busy:
            self.angle=0;self._idle_tooltip=self.toolTip();self.setToolTip('正在导入影像…')
            self.setAccessibleName('正在导入影像')
            if self.isVisible():self.timer.start()
        else:
            self.timer.stop();self.setToolTip(self._idle_tooltip);self.setAccessibleName(self.text())
        self.update()

    def advance(self):
        self.angle=(self.angle+18)%360;self.update()

    def showEvent(self,event):
        super().showEvent(event)
        if self.busy:self.timer.start()

    def hideEvent(self,event):
        self.timer.stop();super().hideEvent(event)

    def paintEvent(self,event):
        if not self.busy:return super().paintEvent(event)
        option=QStyleOptionButton();self.initStyleOption(option);option.text='';option.icon=type(option.icon)()
        painter=QStylePainter(self);painter.drawControl(QStyle.ControlElement.CE_PushButton,option)
        text='正在导入…';width=self.fontMetrics().horizontalAdvance(text)
        left=(self.width()-width-24)/2;center=self.height()/2
        painter.setRenderHint(painter.RenderHint.Antialiasing)
        pen=QPen(QColor('#087f88'),2);pen.setCapStyle(Qt.PenCapStyle.RoundCap);painter.setPen(pen)
        painter.drawArc(QRectF(left,center-7,14,14),-self.angle*16,260*16)
        painter.drawItemText(QRectF(left+24,0,width,self.height()).toRect(),Qt.AlignmentFlag.AlignCenter,
                             option.palette,True,text,QPalette.ColorRole.ButtonText)
