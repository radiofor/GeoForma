"""Full editable source names; constrain only the committed toolbar caption."""
from PySide6.QtCore import Qt,Signal,QTimer,QRect
from PySide6.QtGui import QTextOption
from PySide6.QtWidgets import QDialog,QPlainTextEdit,QVBoxLayout,QLabel,QDialogButtonBox
from ..reference_images import reference_group_name


class ReferenceNameEdit(QPlainTextEdit):
    accepted=Signal()
    heightChanged=Signal()

    def __init__(self,parent=None):
        super().__init__(parent);self.setTabChangesFocus(True)
        self.setWordWrapMode(QTextOption.WrapMode.WrapAnywhere)
        option=self.document().defaultTextOption();option.setAlignment(Qt.AlignmentFlag.AlignHCenter);self.document().setDefaultTextOption(option)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet('QPlainTextEdit{padding:6px;background:white;color:#304c59;border:1px solid #ccdce2;border-radius:5px;selection-background-color:#087f88;selection-color:white;} QPlainTextEdit:focus{border-color:#087f88;}')
        self.textChanged.connect(self.fit_text);self.setFixedHeight(38)

    def text(self):return self.toPlainText()

    def setText(self,text):
        self.setPlainText(text);self.document().setModified(False)

    def isModified(self):return self.document().isModified()

    def fit_text(self):
        rect=self.fontMetrics().boundingRect(QRect(0,0,max(80,self.width()-40),100000),Qt.TextFlag.TextWordWrap|Qt.TextFlag.TextWrapAnywhere,self.text() or ' ')
        height=max(38,min(240,rect.height()+26))
        if height!=self.height():self.setFixedHeight(height);self.heightChanged.emit()

    def resizeEvent(self,event):
        super().resizeEvent(event);self.fit_text()

    def keyPressEvent(self,event):
        if event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter):self.accepted.emit();event.accept();return
        super().keyPressEvent(event)


class ReferenceNameDialog(QDialog):
    def __init__(self,suggested='',parent=None):
        super().__init__(parent);self.setWindowTitle('参考类型')
        layout=QVBoxLayout(self);layout.addWidget(QLabel('名称'))
        self.field=ReferenceNameEdit();layout.addWidget(self.field)
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText('导入');self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        self.buttons.accepted.connect(self.accept);self.buttons.rejected.connect(self.reject);self.field.accepted.connect(self.accept);layout.addWidget(self.buttons)
        self.field.textChanged.connect(self.validate);self.field.heightChanged.connect(self.fit_height)
        self.setTextValue(suggested.strip())
        available=self.screen().availableGeometry().width()-40
        self.resize(min(available,max(390,min(720,self.fontMetrics().horizontalAdvance(suggested)+48))),self.sizeHint().height())

    def textValue(self):return self.field.text()
    def setTextValue(self,text):self.field.setText(text);self.validate()
    def value(self):return reference_group_name(self.textValue(),truncate=True)

    def validate(self):
        try:self.value();valid=True;message=''
        except ValueError as error:valid=False;message=str(error)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(valid);self.field.setToolTip(message)

    def fit_height(self):self.resize(self.width(),self.layout().sizeHint().height())

    def showEvent(self,event):
        super().showEvent(event)
        def focus():
            if self.isVisible():self.field.setFocus(Qt.FocusReason.OtherFocusReason);self.field.selectAll()
        QTimer.singleShot(0,self,focus)

    def accept(self):
        try:self.value()
        except ValueError:self.validate();return
        super().accept()
