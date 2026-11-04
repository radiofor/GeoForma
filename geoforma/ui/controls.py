"""Reusable controls with consistent layout and interaction defaults."""
from PySide6.QtCore import Qt,QSize,QEvent,QRect
from PySide6.QtGui import QPainter,QIcon,QPalette
from PySide6.QtWidgets import QToolButton,QPushButton,QSizePolicy,QDoubleSpinBox,QScrollArea,QFrame,QLabel,QStyle,QStyleOptionButton,QStyleOptionToolButton


class ElidedLabel(QLabel):
    """Keep a compact single line while retaining the original value and tooltip."""
    def __init__(self,text='',parent=None,text_padding=0):
        super().__init__('',parent);self._source_text='';self._display_text='';self._text_padding=text_padding
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0);self.setText(text)

    def setText(self,text):
        text=str(text)
        if text==self._source_text:return
        self._source_text=text;self.setToolTip(self._source_text);self.setAccessibleName(text);self._refresh_text()

    def text(self):return self._source_text

    def sizeHint(self):return QSize(0,super().sizeHint().height())

    def minimumSizeHint(self):return QSize(0,super().minimumSizeHint().height())

    def _refresh_text(self):
        width=max(0,self.contentsRect().width()-self._text_padding)
        text=self.fontMetrics().elidedText(self._source_text,Qt.TextElideMode.ElideRight,width)
        if text!=self._display_text:self._display_text=text;self.update()

    def paintEvent(self,event):
        # QLabel.setText invalidates parent layouts even in a fixed status slot.
        # Paint the changing single line locally; geometry is independent of it.
        super().paintEvent(event)
        painter=QPainter(self);painter.setFont(self.font())
        self.style().drawItemText(painter,self.contentsRect(),int(self.alignment()),self.palette(),self.isEnabled(),self._display_text,self.foregroundRole())

    def resizeEvent(self,event):
        super().resizeEvent(event);self._refresh_text()

    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange,QEvent.Type.StyleChange):self._refresh_text()


class DeviceStatusLabel(ElidedLabel):
    """Fit device status in a compact row while retaining its full accessible text."""
    def _refresh_text(self):
        width=max(0,self.contentsRect().width()-self._text_padding)
        full=self._source_text
        compact=full.replace('GPU 优先','GPU优先').replace('CPU（回退）','CPU回退').replace(' · ','·')
        short=compact.replace('资源未配置','缺资源')
        alternatives=(full,compact,short,short.replace('设备：','设备 '))
        text=next((value for value in alternatives if self.fontMetrics().horizontalAdvance(value)<=width),None)
        if text is None:text=self.fontMetrics().elidedText(alternatives[-1],Qt.TextElideMode.ElideRight,width)
        if text!=self._display_text:self._display_text=text;self.update()


class TrailingIconButton(QPushButton):
    """Draw the normal button and keep its icon against the right edge."""
    def icon_rect(self):
        size=self.iconSize()
        return QRect(self.width()-size.width()-6,(self.height()-size.height())//2,size.width(),size.height())

    def paintEvent(self,event):
        option=QStyleOptionButton();self.initStyleOption(option)
        icon=QIcon(option.icon);option.icon=QIcon()
        painter=QPainter(self)
        painter.save()
        self.style().drawControl(QStyle.ControlElement.CE_PushButton,option,painter,self)
        painter.restore()
        if not icon.isNull():
            rect=self.icon_rect()
            if option.state & QStyle.StateFlag.State_Sunken:
                rect.translate(self.style().pixelMetric(QStyle.PixelMetric.PM_ButtonShiftHorizontal,option,self),
                               self.style().pixelMetric(QStyle.PixelMetric.PM_ButtonShiftVertical,option,self))
            mode=QIcon.Mode.Normal if self.isEnabled() else QIcon.Mode.Disabled
            icon.paint(painter,rect,Qt.AlignmentFlag.AlignCenter,mode)


def action_button(action):
    button=QToolButton();button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
    button.setDefaultAction(action);button.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
    return button


class CenteredIconActionButton(QToolButton):
    """Keep an action's icon and caption together at the center of its button."""
    def __init__(self,action,parent=None):
        super().__init__(parent);self.setDefaultAction(action)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setIconSize(QSize(16,16));self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)

    def paintEvent(self,event):
        painter=QPainter(self);option=QStyleOptionToolButton();self.initStyleOption(option)
        option.text='';option.icon=QIcon()
        self.style().drawComplexControl(QStyle.ComplexControl.CC_ToolButton,option,painter,self)
        icon_size=self.iconSize();text=self.text();gap=7
        width=icon_size.width()+gap+self.fontMetrics().horizontalAdvance(text)
        x=(self.width()-width)//2;y=(self.height()-icon_size.height())//2
        mode=QIcon.Mode.Normal if self.isEnabled() else QIcon.Mode.Disabled
        self.icon().paint(painter,x,y,icon_size.width(),icon_size.height(),Qt.AlignmentFlag.AlignCenter,mode)
        rect=self.rect().adjusted(x+icon_size.width()+gap,0,0,0)
        self.style().drawItemText(painter,rect,int(Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter),self.palette(),self.isEnabled(),text,QPalette.ColorRole.ButtonText)


def percentage_input(tooltip):
    spin=QDoubleSpinBox();spin.setAlignment(Qt.AlignmentFlag.AlignCenter);spin.setRange(0,100);spin.setDecimals(0);spin.setSingleStep(1);spin.setToolTip(tooltip)
    spin.setMinimumWidth(0);spin.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
    return spin


def scroll_panel(widget,minimum,maximum):
    scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);scroll.setMinimumWidth(minimum);scroll.setMaximumWidth(maximum);scroll.setWidget(widget)
    return scroll
