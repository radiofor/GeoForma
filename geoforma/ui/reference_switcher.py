"""Reference buttons, horizontal navigation, and retained drag reordering."""
from PySide6.QtCore import Qt,Signal,QTimer,QPropertyAnimation,QEasingCurve
from PySide6.QtWidgets import QApplication,QScrollArea,QFrame,QWidget,QHBoxLayout,QToolButton,QSizePolicy
from ..reference_images import REFERENCE_NAME_LIMIT,reference_tooltip


class ReferenceButton(QToolButton):
    def __init__(self,owner):
        super().__init__(owner.buttons_widget);self.owner=owner;self.press_global=None;self.press_offset=None;self.dragging=False
        self.setFixedSize(96,30);self.ensurePolished();self.setCheckable(True)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.clicked.connect(lambda checked=False:self.owner.selected.emit(self.reference))

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            self.press_global=event.globalPosition().toPoint();self.press_offset=event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        if self.press_global is not None:
            point=event.globalPosition().toPoint()
            if not self.dragging and (point-self.press_global).manhattanLength()>=QApplication.startDragDistance():
                self.dragging=self.owner.start_drag(self,self.press_offset,point)
                if self.dragging:self.setDown(False)
            if self.dragging:
                self.owner.move_drag(point);event.accept();return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self.dragging:
            self.owner.finish_drag(event.globalPosition().toPoint());self.dragging=False;self.press_global=None
            self.setDown(False);event.accept();return
        self.press_global=None;super().mouseReleaseEvent(event)


class ReferenceSwitcher(QWidget):
    selected=Signal(object)
    reordered=Signal(object)
    button_width=96
    arrow_width=22

    def __init__(self,parent=None):
        super().__init__(parent);self.setFixedHeight(46);self.setSizePolicy(QSizePolicy.Policy.Fixed,QSizePolicy.Policy.Fixed)
        self.buttons_widget=QWidget();self.buttons_widget.setFixedHeight(30);self.row=QHBoxLayout(self.buttons_widget)
        self.row.setContentsMargins(0,0,0,0);self.row.setSpacing(3)
        self.scroll=QScrollArea();self.scroll.setFrameShape(QFrame.Shape.NoFrame);self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setFixedHeight(30);self.scroll.setMinimumWidth(0);self.scroll.setWidget(self.buttons_widget)
        self.left=self._arrow(Qt.ArrowType.LeftArrow);self.right=self._arrow(Qt.ArrowType.RightArrow)
        layout=QHBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(2)
        layout.addWidget(self.left);layout.addWidget(self.scroll,1);layout.addWidget(self.right)
        self.left.clicked.connect(lambda:self.scroll_by(-1));self.right.clicked.connect(lambda:self.scroll_by(1))
        bar=self.scroll.horizontalScrollBar();bar.valueChanged.connect(self._sync_arrows);bar.rangeChanged.connect(self._sync_arrows)
        self.scroll_animation=QPropertyAnimation(bar,b'value',self);self.scroll_animation.setDuration(150)
        self.scroll_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.drag_timer=QTimer(self);self.drag_timer.setInterval(30);self.drag_timer.timeout.connect(self._drag_scroll)
        self.buttons={};self.signature=None;self.natural=0;self.limit=0;self.drag=None;self.shift_animations={}
        self.setFixedWidth(0);self.hide()

    def _arrow(self,direction):
        button=QToolButton(self);button.setArrowType(direction);button.setFixedSize(self.arrow_width,30)
        button.setAutoRepeat(True);button.setProperty('feedback','navigation')
        button.setStyleSheet('QToolButton{padding:0;border:1px solid #d5e3e7;border-radius:4px;background:white;color:#30525c;} QToolButton:disabled{background:#f5f8f9;color:#a8bcc1;}')
        button.setAccessibleName('向左移动参考' if direction==Qt.ArrowType.LeftArrow else '向右移动参考')
        return button

    def viewport(self):return self.scroll.viewport()

    def set_references(self,records,current,enabled):
        signature=tuple((record['group'],record['path'],record['fingerprint'],id(record),reference_tooltip(record)) for record in records)
        if signature!=self.signature:
            self.cancel_drag();self._stop_shifts();self.signature=signature;old=self.buttons;buttons={}
            while self.row.count():self.row.takeAt(0)
            for record in records:
                key=(record['group'].casefold(),record['path']);button=old.pop(key,None)
                if button is None:button=ReferenceButton(self)
                button.reference=record;name=record['group']
                caption=name if len(name)<=REFERENCE_NAME_LIMIT else name[:REFERENCE_NAME_LIMIT-1]+'…'
                button.setText(button.fontMetrics().elidedText(caption,Qt.TextElideMode.ElideRight,button.width()-18))
                button.setToolTip(reference_tooltip(record));self.row.addWidget(button);buttons[key]=button
            for button in old.values():button.hide();button.deleteLater()
            self.buttons=buttons;self.natural=len(buttons)*self.button_width+max(0,len(buttons)-1)*self.row.spacing()
            self.buttons_widget.setMinimumWidth(self.natural);self.fit_width()
        self.set_current(current)
        for button in self.buttons.values():button.setEnabled(enabled)
        if not enabled:self.cancel_drag()

    def set_current(self,current):
        for button in self.buttons.values():
            checked=button.reference is current
            if button.isChecked()!=checked:button.setChecked(checked)

    def set_width_limit(self,limit):
        limit=max(0,int(limit))
        if self.limit!=limit:self.limit=limit;self.fit_width()

    def fit_width(self):
        arrows=2*self.arrow_width+2*self.layout().spacing()
        full=self.natural+arrows
        target=min(self.limit,full)
        overflow=bool(target and full>target)
        if overflow:
            available=target-arrows
            if available>=self.button_width:
                pitch=self.button_width+self.row.spacing();count=(available+self.row.spacing())//pitch
                target=count*pitch-self.row.spacing()+arrows
        self.left.setVisible(bool(target));self.right.setVisible(bool(target))
        if self.width()!=target:self.setFixedWidth(target)
        self.buttons_widget.setVisible(bool(self.buttons))
        self.setVisible(bool(target));self.layout().activate()
        QTimer.singleShot(0,self._sync_arrows)

    def _sync_arrows(self,*args):
        bar=self.scroll.horizontalScrollBar()
        self.left.setEnabled(bar.value()>bar.minimum());self.right.setEnabled(bar.value()<bar.maximum())

    def scroll_by(self,direction):
        bar=self.scroll.horizontalScrollBar()
        origin=self.scroll_animation.endValue() if self.scroll_animation.state()==QPropertyAnimation.State.Running else bar.value()
        target=max(bar.minimum(),min(bar.maximum(),int(origin)+direction*(self.button_width+self.row.spacing())))
        self.scroll_animation.stop();self.scroll_animation.setStartValue(bar.value());self.scroll_animation.setEndValue(target);self.scroll_animation.start()

    def start_drag(self,button,offset,point):
        index=self.row.indexOf(button)
        if self.drag is not None or index<0 or len(self.buttons)<2:return False
        self._stop_shifts()
        self.scroll_animation.stop();placeholder=QWidget(self.buttons_widget);placeholder.setFixedSize(button.size())
        self.row.removeWidget(button);self.row.insertWidget(index,placeholder);placeholder.show();self.row.activate()
        button.raise_();self.drag={'button':button,'placeholder':placeholder,'offset':offset,'point':point,
                                  'original':list(self.buttons.values()),'direction':0,'origin':button.x()+offset.x()}
        return True

    def move_drag(self,point):
        if not self.drag:return
        drag=self.drag;drag['point']=point;viewport_point=self.viewport().mapFromGlobal(point)
        edge=20;direction=-1 if viewport_point.x()<edge else 1 if viewport_point.x()>self.viewport().width()-edge else 0
        bar=self.scroll.horizontalScrollBar()
        drag['direction']=direction if (direction<0 and bar.value()>bar.minimum() or direction>0 and bar.value()<bar.maximum()) else 0
        if drag['direction'] and not self.drag_timer.isActive():self.drag_timer.start()
        elif not drag['direction']:self.drag_timer.stop()
        local=self.buttons_widget.mapFromGlobal(point);button=drag['button']
        x=max(0,min(self.buttons_widget.width()-button.width(),local.x()-drag['offset'].x()))
        if button.x()!=x:button.move(x,0)
        placeholder=drag['placeholder'];slot=self.row.indexOf(placeholder);count=self.row.count()
        pitch=self.button_width+self.row.spacing();center=(self.button_width-1)//2
        passed=(local.x()-center-(0 if local.x()>=drag['origin'] else 1))//pitch+1
        passed=max(0,min(count,passed));position=passed-(slot<passed)
        if slot!=position:
            affected=[self.row.itemAt(i).widget() for i in range(min(slot,position),max(slot,position)+1)]
            affected=[button for button in affected if button is not placeholder]
            before={button:button.pos() for button in affected};self._stop_shifts()
            self.row.removeWidget(placeholder);self.row.insertWidget(position,placeholder);self.row.invalidate();self.row.activate()
            for button in affected:
                target=button.pos();start=before[button]
                if target==start:continue
                button.move(start);animation=QPropertyAnimation(button,b'pos',self);animation.setDuration(110)
                animation.setEasingCurve(QEasingCurve.Type.OutCubic);animation.setStartValue(start);animation.setEndValue(target)
                self.shift_animations[button]=animation
                animation.finished.connect(lambda button=button,animation=animation:self._shift_finished(button,animation))
                animation.start()

    def _shift_finished(self,button,animation):
        if self.shift_animations.get(button) is animation:self.shift_animations.pop(button,None)
        animation.deleteLater()

    def _stop_shifts(self):
        for animation in self.shift_animations.values():animation.stop();animation.deleteLater()
        self.shift_animations.clear();self.row.invalidate();self.row.activate()

    def _drag_scroll(self):
        if not self.drag:self.drag_timer.stop();return
        bar=self.scroll.horizontalScrollBar();before=bar.value();bar.setValue(before+self.drag['direction']*12)
        if bar.value()!=before:self.move_drag(self.drag['point'])
        else:self.drag_timer.stop()

    def finish_drag(self,point):
        if not self.drag:return
        viewport_point=self.viewport().mapFromGlobal(point)
        if viewport_point.y() < -20 or viewport_point.y() > self.viewport().height()+20:
            self.cancel_drag();return
        self.move_drag(point);self._stop_shifts();drag=self.drag;self.drag=None;self.drag_timer.stop()
        placeholder=drag['placeholder'];index=self.row.indexOf(placeholder);self.row.removeWidget(placeholder);placeholder.deleteLater()
        self.row.insertWidget(index,drag['button']);self.row.activate()
        self.snap_scroll()
        ordered=[self.row.itemAt(i).widget() for i in range(self.row.count())]
        if ordered!=drag['original']:self.reordered.emit([button.reference['group'].casefold() for button in ordered])

    def cancel_drag(self):
        if not self.drag:return
        self._stop_shifts();drag=self.drag;self.drag=None;self.drag_timer.stop();placeholder=drag['placeholder']
        self.row.removeWidget(placeholder);placeholder.deleteLater()
        for index,button in enumerate(drag['original']):
            self.row.removeWidget(button);self.row.insertWidget(index,button)
        drag['button'].dragging=False;drag['button'].press_global=None;drag['button'].setDown(False);self.row.activate();self.snap_scroll()

    def snap_scroll(self):
        bar=self.scroll.horizontalScrollBar();pitch=self.button_width+self.row.spacing()
        target=max(bar.minimum(),min(bar.maximum(),round(bar.value()/pitch)*pitch))
        if target!=bar.value():
            self.scroll_animation.stop();self.scroll_animation.setStartValue(bar.value());self.scroll_animation.setEndValue(target);self.scroll_animation.start()
