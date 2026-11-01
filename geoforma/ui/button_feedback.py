"""Shared hover and press feedback without moving or restyling controls."""
from PySide6.QtCore import QObject,QEvent,Qt,QRectF,QVariantAnimation,QEasingCurve,QTimer
from PySide6.QtGui import QColor,QPainter,QPen,QAction,QCursor
from PySide6.QtWidgets import (QWidget,QAbstractButton,QCheckBox,QRadioButton,QDialogButtonBox,
    QToolButton,QPushButton,QTabBar,QAbstractSpinBox,QStyle,QStyleOptionButton,QStyleOptionSpinBox)

COLORS={'normal':'#168F93','primary':'#64DBC4','import':'#087F88','danger':'#CE4F60',
        'toggle':'#208FA6','navigation':'#557CA8','dialog':'#8871AF','cancel':'#788B99','candidate':'#C1913E'}


def feedback_kind(button):
    explicit=button.property('feedback')
    if isinstance(button,QToolButton) and button.defaultAction():explicit=explicit or button.defaultAction().property('feedback')
    if explicit in COLORS:return explicit
    role=button.property('role')
    if role in ('danger','import'):return role
    if button.objectName()=='primary':return 'primary'
    parent=button.parentWidget()
    if isinstance(parent,QDialogButtonBox):
        role=parent.buttonRole(button)
        if role==QDialogButtonBox.ButtonRole.DestructiveRole:return 'danger'
        if role in (QDialogButtonBox.ButtonRole.AcceptRole,QDialogButtonBox.ButtonRole.YesRole):return 'import'
        if role in (QDialogButtonBox.ButtonRole.RejectRole,QDialogButtonBox.ButtonRole.NoRole):return 'cancel'
    if button.isCheckable():return 'toggle'
    if isinstance(button,QToolButton) and button.menu():return 'dialog'
    return 'normal'


class PressFeedback(QWidget):
    def __init__(self,control):
        # QWidget construction sends synchronous events. A nested event loop may
        # paint the overlay before the base constructor returns, so the paint
        # state must already exist when the widget is attached to its parent.
        self.control=control;self.strength=0.;self.target=None;self.kind='normal'
        self.hovered=False;self.hover_target=None;self.hover_kind='normal'
        super().__init__(control)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.animation=QVariantAnimation(self);self.animation.setDuration(200);self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(self.advance);self.animation.finished.connect(self.finish)

    def attach(self):
        self.setGeometry(self.control.rect())
        if not self.isVisible():self.show();self.raise_()

    def hover(self,active,kind=None,target=None):
        if not self.control.isVisible():active=False
        kind=kind or feedback_kind(self.control)
        if (self.hovered,self.hover_kind,self.hover_target)==(active,kind,target):return
        self.hovered=active;self.hover_kind=kind;self.hover_target=target
        self.update()

    def reset(self):
        self.animation.stop();self.strength=0.;self.hovered=False;self.update()

    def finish(self):
        self.strength=0.
        self.update()

    def hold(self,kind=None,target=None):
        if not self.control.isEnabled() or not self.control.isVisible():return
        self.animation.stop();self.kind=kind or feedback_kind(self.control);self.target=target;self.strength=1.
        self.attach()
        # Paint before clicked/triggered handlers can start synchronous work.
        # Local repaint avoids processing unrelated input or re-entering tasks.
        self.repaint()

    def release(self):
        if not self.isVisible() or self.strength<=0:return
        self.animation.setStartValue(self.strength);self.animation.setEndValue(0.);self.animation.start()

    def pulse(self,kind=None,target=None):self.hold(kind,target);self.release()

    def advance(self,value):self.strength=float(value);self.update()

    def feedback_rect(self):
        target=self.target if self.strength>0 else self.hover_target
        bounds=QRectF(self.rect()).adjusted(1.5,1.5,-1.5,-1.5)
        rect=QRectF(target or self.rect()).adjusted(1.5,1.5,-1.5,-1.5)
        if isinstance(self.control,(QCheckBox,QRadioButton)):
            option=QStyleOptionButton();option.initFrom(self.control)
            element=QStyle.SubElement.SE_CheckBoxIndicator if isinstance(self.control,QCheckBox) else QStyle.SubElement.SE_RadioButtonIndicator
            rect=QRectF(self.control.style().subElementRect(element,option,self.control)).adjusted(-2,-2,2,2)
        return rect.intersected(bounds)

    def paintEvent(self,event):
        # Do not query the QWidget while its base constructor is still running.
        if self.strength<=0 and not self.hovered:return
        rect=self.feedback_rect()
        kind=self.kind if self.strength>0 else self.hover_kind
        strength=max(self.strength,(.4 if self.control.isEnabled() else .2) if self.hovered else 0.)
        if strength<=0:return
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color=QColor(COLORS[kind]);color.setAlphaF(.85*strength);painter.setPen(QPen(color,1.5))
        color=QColor(COLORS[kind]);color.setAlphaF((.2 if kind in ('primary','danger') else .12)*strength)
        painter.setBrush(color);painter.drawRoundedRect(rect,5,5)


class ButtonFeedback(QObject):
    def overlay(self,control):
        overlay=getattr(control,'_geoforma_feedback',None)
        if overlay is None:overlay=PressFeedback(control);control._geoforma_feedback=overlay
        return overlay

    def bind(self,button):
        menu=button.menu() if isinstance(button,(QToolButton,QPushButton)) else None
        if menu is not None and getattr(button,'_geoforma_feedback_menu',None) is not menu:
            button._geoforma_feedback_menu=menu
            def restore():
                # Instant-popup buttons may never receive released/leave while
                # the menu owns the mouse grab. Do not retain their press glow.
                overlay=self.overlay(button);overlay.reset()
                overlay.hover(button.rect().contains(button.mapFromGlobal(QCursor.pos())))
            menu.aboutToHide.connect(lambda:QTimer.singleShot(0,button,restore))
        if getattr(button,'_geoforma_feedback_bound',False):return
        button._geoforma_feedback_bound=True
        self.overlay(button)
        # pressed/released also cover Space, Enter and programmatic animateClick.
        button.pressed.connect(lambda:self.overlay(button).hold())
        button.released.connect(lambda:self.overlay(button).release())

    def eventFilter(self,obj,event):
        kind=event.type()
        if kind in (QEvent.Type.Polish,QEvent.Type.Show):
            if isinstance(obj,QAbstractButton):self.bind(obj)
            elif isinstance(obj,QTabBar):obj.setMouseTracking(True)
            if kind==QEvent.Type.Show and isinstance(obj,(QAbstractButton,QTabBar)):self.overlay(obj).attach()
        elif kind in (QEvent.Type.Enter,QEvent.Type.Leave,QEvent.Type.HoverEnter,QEvent.Type.HoverLeave,QEvent.Type.MouseMove,QEvent.Type.HoverMove) and isinstance(obj,QAbstractButton):
            active=kind not in (QEvent.Type.Leave,QEvent.Type.HoverLeave)
            if kind in (QEvent.Type.MouseMove,QEvent.Type.HoverMove):active=obj.rect().contains(event.position().toPoint())
            self.overlay(obj).hover(active)
        elif kind in (QEvent.Type.Enter,QEvent.Type.MouseMove,QEvent.Type.Leave) and isinstance(obj,QTabBar):
            index=obj.tabAt(event.position().toPoint()) if kind!=QEvent.Type.Leave else -1
            self.overlay(obj).hover(index>=0 and obj.isTabEnabled(index),'toggle',obj.tabRect(index) if index>=0 else None)
        elif kind==QEvent.Type.Resize and isinstance(obj,QWidget):
            overlay=getattr(obj,'_geoforma_feedback',None)
            if overlay is not None:overlay.setGeometry(obj.rect())
        elif kind in (QEvent.Type.Hide,QEvent.Type.EnabledChange) and isinstance(obj,QWidget):
            overlay=getattr(obj,'_geoforma_feedback',None)
            if overlay is not None:
                overlay.reset()
                if kind==QEvent.Type.EnabledChange and isinstance(obj,QAbstractButton):overlay.hover(obj.underMouse())
        elif kind==QEvent.Type.Shortcut and isinstance(obj,QAction) and obj.isEnabled():
            for target in obj.associatedObjects():
                if isinstance(target,QAbstractButton) and target.isVisible():self.overlay(target).pulse()
        elif kind==QEvent.Type.MouseButtonPress and event.button()==Qt.MouseButton.LeftButton and isinstance(obj,QWidget) and obj.isEnabled():
            rect=None
            if isinstance(obj,QTabBar):
                index=obj.tabAt(event.position().toPoint())
                if index>=0 and obj.isTabEnabled(index):rect=obj.tabRect(index)
            elif isinstance(obj,QAbstractSpinBox):
                option=QStyleOptionSpinBox();obj.initStyleOption(option)
                for sub in (QStyle.SubControl.SC_SpinBoxUp,QStyle.SubControl.SC_SpinBoxDown):
                    candidate=obj.style().subControlRect(QStyle.ComplexControl.CC_SpinBox,option,sub,obj)
                    if candidate.contains(event.position().toPoint()):rect=candidate;break
            if rect is not None:self.overlay(obj).pulse('toggle',rect)
        return False


def install_button_feedback(app):
    if hasattr(app,'_geoforma_button_feedback'):return
    feedback=ButtonFeedback(app);app._geoforma_button_feedback=feedback;app.installEventFilter(feedback)
    for widget in app.allWidgets():
        if isinstance(widget,QAbstractButton):feedback.bind(widget)
