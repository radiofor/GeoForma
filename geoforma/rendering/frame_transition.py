"""Short, interruptible viewport transition after a replacement frame is ready."""
from PySide6.QtCore import QEasingCurve,QEvent,QVariantAnimation,Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget


class FrameTransition(QWidget):
    def __init__(self,view,require_raster=True):
        super().__init__(view.viewport());self.view=view;self.require_raster=require_raster;self.frame=None;self.opacity=0.
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.animation=QVariantAnimation(self);self.animation.setDuration(300)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutSine)
        self.animation.valueChanged.connect(self._advance);self.animation.finished.connect(self.cancel)
        self.view.installEventFilter(self);self.view.viewport().installEventFilter(self);self.hide()

    def capture(self):
        # Include any transition already in progress, so a fast subsequent
        # frame starts from what is actually visible rather than jumping to
        # the previous target. QWidget.grab includes child widgets.
        ready=not self.require_raster or self.view.layers.base_item is not None
        frame=self.view.viewport().grab() if self.view.isVisible() and ready else None
        self.cancel();self.frame=frame

    def reveal(self):
        if self.frame is None:return
        self.setGeometry(self.view.viewport().rect());self.opacity=1.;self.show();self.raise_()
        self.animation.setStartValue(1.);self.animation.setEndValue(0.);self.animation.start()

    def cancel(self):
        self.animation.stop();self.hide();self.frame=None;self.opacity=0.

    def _advance(self,value):self.opacity=float(value);self.update()

    def paintEvent(self,event):
        if self.frame is None:return
        painter=QPainter(self);painter.setOpacity(self.opacity);painter.drawPixmap(0,0,self.frame);painter.end()

    def eventFilter(self,obj,event):
        if self.frame is not None and (event.type() in (QEvent.Type.MouseButtonPress,QEvent.Type.MouseButtonDblClick,
                QEvent.Type.Wheel,QEvent.Type.KeyPress,QEvent.Type.Hide) or event.type()==QEvent.Type.Resize and self.isVisible()):self.cancel()
        return False
