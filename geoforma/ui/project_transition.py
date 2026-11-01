"""Keep the old complete frame visible until its replacement is ready."""
from PySide6.QtCore import Qt,QEvent,QTimer,QPropertyAnimation,QEasingCurve,Property
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget,QLabel
from .text import ui_text
from .sidebar_transition import SidebarTransition,sidebar_layout


class ProjectTransition(QWidget):
    def __init__(self,parent,recovering=False):
        self.snapshot=parent.grab();self.old_sidebar=sidebar_layout(parent)
        super().__init__(parent);self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self._fit_to_workbench();self.setFocusPolicy(Qt.FocusPolicy.StrongFocus);self.setCursor(Qt.CursorShape.BusyCursor)
        self.task_title=ui_text('project.restoring' if recovering else 'project.loading')
        self.caption=QLabel(self.task_title,self);self.caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.caption.setTextFormat(Qt.TextFormat.PlainText)
        self.caption.setStyleSheet('QLabel{color:#eaf7f7;background:#153c49;border:1px solid #35707a;border-radius:8px;padding:10px 18px;}')
        self.caption.setFixedSize(min(460,max(180,self.width()-32)),68);self.caption.hide();self._position_caption();self.show();self.raise_();self.setFocus()
        self.badge_timer=QTimer(self);self.badge_timer.setSingleShot(True);self.badge_timer.setInterval(120);self.badge_timer.timeout.connect(self.caption.show);self.badge_timer.start()
        parent.installEventFilter(self);parent.statusBar().installEventFilter(self)
        self.animation=None;self.next_snapshot=None;self.sidebar=None;self._blend=1.

    def _position_caption(self):self.caption.move((self.width()-self.caption.width())//2,max(16,self.height()-self.caption.height()-52))

    def _fit_to_workbench(self):
        parent=self.parentWidget();bar=parent.statusBar()
        # Keep the viewport frozen while the real named progress and cancel
        # control remain visible and interactive beneath the transition.
        height=bar.geometry().top() if bar.isVisible() else parent.height()
        self.setGeometry(0,0,parent.width(),height)

    def set_stage(self,text):
        full=str(text);metrics=self.caption.fontMetrics()
        stage=metrics.elidedText(full,Qt.TextElideMode.ElideMiddle,max(0,self.caption.width()-40))
        self.caption.setText(self.task_title+'\n'+stage);self.caption.setToolTip(full)

    def paintEvent(self,event):
        painter=QPainter(self);frame=self.parentWidget().rect()
        if self.next_snapshot is not None:painter.drawPixmap(frame,self.next_snapshot)
        painter.setOpacity(self._blend);painter.drawPixmap(frame,self.snapshot)
        if self.sidebar and self.parentWidget().size()==self.snapshot.deviceIndependentSize().toSize():
            self.sidebar.paint(painter,frame,self.snapshot,self.next_snapshot,self._blend)

    def set_blend(self,value):self._blend=value;self.update()
    blend=Property(float,lambda self:self._blend,set_blend)

    def eventFilter(self,obj,event):
        if obj is self.parentWidget() and event.type()==QEvent.Type.Resize:self._fit_to_workbench();self._position_caption()
        elif obj is self.parentWidget().statusBar() and event.type() in (QEvent.Type.Move,QEvent.Type.Resize):self._fit_to_workbench();self._position_caption()
        return False

    def event(self,event):
        if event.type()==QEvent.Type.ShortcutOverride:event.accept();return True
        return super().event(event)

    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Escape:self.parentWidget().cancel()
        event.accept()

    def finish(self,callback=None,animate=True):
        if self.animation is not None:self.animation.stop()
        self.badge_timer.stop();self.caption.hide()
        def done():
            parent=self.parentWidget()
            if parent:parent.removeEventFilter(self);parent.statusBar().removeEventFilter(self)
            self.hide();self.deleteLater()
            if callback:callback()
        if not animate:done();return
        # Composite two finished frames. The underlying scene never needs to
        # repaint its potentially thousands of polygons for every animation tick.
        self.hide();self.next_snapshot=self.parentWidget().grab()
        self.sidebar=SidebarTransition.create(self.old_sidebar,sidebar_layout(self.parentWidget()))
        self.show();self.raise_();self.setFocus()
        self.animation=QPropertyAnimation(self,b'blend',self);self.animation.setDuration(240 if self.sidebar else 140)
        self.animation.setStartValue(1.);self.animation.setEndValue(0.);self.animation.setEasingCurve(QEasingCurve.Type.InOutCubic if self.sidebar else QEasingCurve.Type.OutCubic)
        self.animation.finished.connect(done);self.animation.start()
