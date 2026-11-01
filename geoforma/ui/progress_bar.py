"""The sole progress-bar renderer, shared by light and dark hosts."""
from PySide6.QtCore import Qt,QRectF,QTimer,QVariantAnimation,QEasingCurve,QAbstractAnimation,QSignalBlocker,Signal
from PySide6.QtGui import QColor,QPainter,QPen,QPainterPath
from PySide6.QtWidgets import QProgressBar,QSizePolicy
from ..progress import ProgressModel


PALETTES={
    'light':dict(track='#e2ecef',idle='#b8cbd0',running='#148e98',complete='#279375',cancelled='#bc9141',failed='#c86470'),
    'dark':dict(track='#2a4859',idle='#7c9da9',running='#37c4bf',complete='#4ecba1',cancelled='#e0b56c',failed='#ef93a0'),
}
COMPLETION_HOLD_MS=120
COMPLETION_FILL_MS=80


class TaskProgressBar(QProgressBar):
    completionPainted=Signal()

    def __init__(self,parent=None,*,variant='light',expanding=False,model=None,smooth=False):
        super().__init__(parent);self.phase='idle';self.offset=0;self.colors=PALETTES[variant]
        self.smooth=smooth;self.display_fraction=0.;self.target_fraction=0.;self._generation=None;self._completion_announced=False
        self.fill_animation=QVariantAnimation(self);self.fill_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.fill_animation.valueChanged.connect(self._advance_fill)
        self.setFixedHeight(18)
        if expanding:self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
        else:self.setFixedWidth(144)
        self.setTextVisible(False);self.setStyleSheet('QProgressBar{border:0;background:transparent;min-height:18px;max-height:18px;}')
        self.timer=QTimer(self);self.timer.setInterval(40);self.timer.timeout.connect(self._tick)
        self.model=model or ProgressModel(self);self.model.changed.connect(self._apply_state);self._apply_state(self.model.state)

    def _apply_state(self,state):
        if self._generation!=self.model.generation:
            self._generation=self.model.generation;self.fill_animation.stop();self.display_fraction=0.;self.target_fraction=0.;self._completion_announced=False
        self.phase=state.phase
        if state.phase in ('complete','cancelled','failed'):
            self.setRange(0,100);self.setValue(round((state.fraction or 0)*100))
        elif state.phase=='idle':self.setRange(0,100);self.setValue(0)
        elif not state.total:self.setRange(0,0);self.setValue(0)
        elif state.total<=2147483647:self.setRange(0,state.total);self.setValue(state.current)
        else:self.setRange(0,10000);self.setValue(round(state.fraction*10000))
        description=state.title+(' · '+state.stage if state.stage else '')
        self.setToolTip(description);self.setAccessibleName(state.title or '任务进度');self.setAccessibleDescription(description)
        if self.smooth:
            if state.phase in ('failed','cancelled'):
                self.fill_animation.stop();self.target_fraction=self.display_fraction
            else:self._animate_fill(state.fraction or 0.)
        self._sync_animation();self.update()

    def _advance_fill(self,value):self.display_fraction=float(value);self.update()

    def _animate_fill(self,target):
        target=max(0.,min(1.,target));same=target==self.target_fraction;self.target_fraction=target
        if not self.isVisible():return
        if same and self.fill_animation.state()!=QAbstractAnimation.State.Stopped:
            remaining=self.fill_animation.duration()-self.fill_animation.currentTime()
            if self.phase!='complete' or remaining<=COMPLETION_FILL_MS:return
        self.fill_animation.stop()
        if abs(target-self.display_fraction)<1e-6:self.display_fraction=target;self.update();return
        blocker=QSignalBlocker(self.fill_animation)
        duration=COMPLETION_FILL_MS if self.phase=='complete' else 80+round(80*abs(target-self.display_fraction))
        self.fill_animation.setDuration(duration)
        self.fill_animation.setStartValue(self.display_fraction);self.fill_animation.setEndValue(target);self.fill_animation.setCurrentTime(0)
        del blocker;self.fill_animation.start()

    def _sync_animation(self):
        animate=self.phase=='running' and self.minimum()==self.maximum() and self.isVisible()
        if animate and not self.timer.isActive():self.timer.start()
        elif not animate:self.timer.stop()

    def _tick(self):self.offset=(self.offset+1)%60;self.update()
    def showEvent(self,event):
        super().showEvent(event);self._sync_animation()
        if self.smooth:self._animate_fill(self.target_fraction)
    def hideEvent(self,event):self.timer.stop();self.fill_animation.stop();super().hideEvent(event)

    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        track=QRectF(2,(self.height()-6)/2,self.width()-4,6)
        color=QColor(self.colors['cancelled' if self.model.state.cancelling else self.phase]);painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self.colors['track']));painter.drawRoundedRect(track,3,3)
        if self.phase=='idle':return
        span=self.maximum()-self.minimum();ratio=max(0.,min(1.,(self.value()-self.minimum())/span)) if span else 0.
        if self.smooth:ratio=self.display_fraction
        painter.setBrush(color)
        if self.phase=='running' and not span:
            painter.save();path=QPainterPath();path.addRoundedRect(track,3,3);painter.setClipPath(path)
            width=track.width()*.32;x=track.left()-width+(track.width()+width)*self.offset/59
            painter.drawRoundedRect(QRectF(x,track.top(),width,track.height()),3,3);painter.restore()
        else:
            fill=QRectF(track);fill.setWidth(track.width()*ratio);painter.drawRoundedRect(fill,3,3)
        if self.phase=='complete' and ratio>=1.:
            cx=track.right()-6;cy=track.center().y();painter.setBrush(color);painter.drawEllipse(QRectF(cx-7,cy-7,14,14))
            pen=QPen(QColor('white'),1.6);pen.setCapStyle(Qt.PenCapStyle.RoundCap);pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin);painter.setPen(pen)
            check=QPainterPath();check.moveTo(cx-3,cy);check.lineTo(cx-1,cy+2);check.lineTo(cx+3.5,cy-2.5);painter.drawPath(check)
            if self.smooth and not self._completion_announced:
                self._completion_announced=True;generation=self.model.generation
                # Notify on the next event turn, after the full bar/checkmark
                # has actually been painted, rather than at logical completion.
                def painted():
                    if self.model.generation==generation and self.phase=='complete':
                        if self.isVisible():self.completionPainted.emit()
                        else:self._completion_announced=False
                QTimer.singleShot(0,self,painted)
