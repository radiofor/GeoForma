"""Native Qt palette/RGB/hex picker and compact category color previews."""
from functools import lru_cache
from PySide6.QtCore import Qt,QRectF,QSignalBlocker
from PySide6.QtGui import QColor,QIcon,QPixmap,QPainter,QPen
from PySide6.QtWidgets import QColorDialog,QToolButton,QLineEdit,QLabel,QSpinBox
from .text import ui_text


@lru_cache(maxsize=128)
def color_icon(color):
    pixmap=QPixmap(40,28);pixmap.setDevicePixelRatio(2);pixmap.fill(Qt.GlobalColor.transparent)
    painter=QPainter(pixmap);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor('#77929c'),1));painter.setBrush(QColor(color));painter.drawRoundedRect(QRectF(.5,.5,19,13),2,2);painter.end()
    icon=QIcon()
    for mode in (QIcon.Mode.Normal,QIcon.Mode.Disabled,QIcon.Mode.Active,QIcon.Mode.Selected):icon.addPixmap(pixmap,mode)
    return icon


class ColorSwatch(QToolButton):
    def __init__(self,color,name='',parent=None):
        super().__init__(parent);self.setFixedSize(26,20)
        self.setProperty('feedback','navigation')
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(ui_text('classes.color_accessible').format(name));self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.set_color(color)

    def set_color(self,color):
        self.color=QColor(color)
        self.setStyleSheet(f'QToolButton{{background:{self.color.name()};border:1px solid #77929c;border-radius:4px;padding:0;}} QToolButton:hover{{border:2px solid #172f3d;}} QToolButton:focus{{border:2px dashed #172f3d;}}')
        self.setToolTip(ui_text('classes.color_hint').format(self.color.name().upper(),self.color.red(),self.color.green(),self.color.blue()))


def _uppercase_hex(field):
    text=field.text();uppercase=text.upper()
    if text==uppercase:return
    cursor=field.cursorPosition();start=field.selectionStart();length=len(field.selectedText())
    with QSignalBlocker(field):
        field.setText(uppercase)
        if start>=0:field.setSelection(start,length)
        else:field.setCursorPosition(cursor)


def choose_color(color,name,parent=None):
    # Reuse Qt's complete picker: swatches, numeric R/G/B fields, and HTML hex.
    dialog=QColorDialog(QColor(color),parent);dialog.setWindowTitle(ui_text('classes.color_title').format(name))
    dialog.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog,True)
    dialog.setOption(QColorDialog.ColorDialogOption.ShowAlphaChannel,False)
    for field in dialog.findChildren(QLineEdit):
        if field.text().startswith('#'):
            field.setPlaceholderText('#RRGGBB');field.setToolTip(ui_text('classes.hex_hint'));field.setAlignment(Qt.AlignmentFlag.AlignCenter)
            _uppercase_hex(field);field.textChanged.connect(lambda text,field=field:_uppercase_hex(field))
    for spin in dialog.findChildren(QSpinBox):spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
    for label in dialog.findChildren(QLabel):
        if label.text().startswith('HTML'):label.setText('HEX:')
    from .modal import dialog_result
    return dialog_result(dialog,lambda current:current.selectedColor().name().upper())[1]
