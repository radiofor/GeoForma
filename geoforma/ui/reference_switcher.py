"""Retained reference buttons and smooth, bounded-width presentation only."""
from PySide6.QtCore import Qt,Signal,QVariantAnimation,QEasingCurve
from PySide6.QtWidgets import QScrollArea,QFrame,QWidget,QHBoxLayout,QToolButton
from ..reference_images import REFERENCE_NAME_LIMIT,reference_tooltip


class ReferenceSwitcher(QScrollArea):
    selected=Signal(object)

    def __init__(self,parent=None):
        super().__init__(parent);self.buttons_widget=QWidget();self.row=QHBoxLayout(self.buttons_widget)
        self.row.setContentsMargins(0,0,0,0);self.row.setSpacing(3);self.setWidget(self.buttons_widget)
        self.setFrameShape(QFrame.Shape.NoFrame);self.setWidgetResizable(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);self.setFixedHeight(46)
        self.buttons={};self.signature=None;self.natural=0;self.limit=320;self.setFixedWidth(0);self.hide()
        self.animation=QVariantAnimation(self);self.animation.setDuration(160);self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(lambda value:self.setFixedWidth(min(int(value),self.limit)))
        self.animation.finished.connect(lambda:self.setVisible(bool(self.buttons)))

    def set_references(self,records,current,enabled):
        signature=tuple((record['group'],record['path'],record['fingerprint'],id(record),reference_tooltip(record)) for record in records)
        if signature!=self.signature:
            self.signature=signature;old=self.buttons;buttons={}
            while self.row.count():self.row.takeAt(0)
            for record in records:
                key=(record['group'].casefold(),record['path']);button=old.pop(key,None)
                if button is None:
                    button=QToolButton(self.buttons_widget);button.setFixedSize(96,30);button.ensurePolished()
                    button.setCheckable(True);button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
                    button.clicked.connect(lambda checked=False,button=button:self.selected.emit(button.reference))
                button.reference=record;name=record['group']
                caption=name if len(name)<=REFERENCE_NAME_LIMIT else name[:REFERENCE_NAME_LIMIT-1]+'…'
                button.setText(button.fontMetrics().elidedText(caption,Qt.TextElideMode.ElideRight,button.width()-18))
                button.setToolTip(reference_tooltip(record));self.row.addWidget(button);buttons[key]=button
            for button in old.values():button.hide();button.deleteLater()
            self.buttons=buttons;self.natural=len(buttons)*96+max(0,len(buttons)-1)*self.row.spacing()
            self.buttons_widget.setMinimumWidth(self.natural);self.fit_width(True)
        self.set_current(current)
        for button in self.buttons.values():button.setEnabled(enabled)

    def set_current(self,current):
        for button in self.buttons.values():
            checked=button.reference is current
            if button.isChecked()!=checked:button.setChecked(checked)

    def set_width_limit(self,limit):self.limit=limit;self.fit_width(False)

    def fit_width(self,animate):
        target=min(self.limit,self.natural+4) if self.buttons else 0
        if self.animation.state()==QVariantAnimation.State.Running and not animate:
            self.animation.setEndValue(target);return
        self.animation.stop()
        if animate and (self.isVisible() or self.buttons):
            start=self.width() if self.isVisible() else 0;self.show()
            self.animation.setStartValue(start);self.animation.setEndValue(target);self.animation.start()
        else:self.setFixedWidth(target);self.setVisible(bool(self.buttons))
