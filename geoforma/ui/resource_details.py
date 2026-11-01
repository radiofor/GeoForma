"""Fixed three-line resource readout; long filenames never resize the dialog."""
from PySide6.QtWidgets import QWidget,QVBoxLayout
from .controls import ElidedLabel


class ResourceDetails(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self._text='';self.lines=[]
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(2)
        for index in range(3):
            label=ElidedLabel();label.setProperty('role','sectionTitle' if index==0 else 'muted');label.setFixedHeight(20)
            layout.addWidget(label);self.lines.append(label)
        self.setFixedHeight(68)

    def setText(self,text):
        self._text=str(text)
        for label,line in zip(self.lines,(self._text.splitlines()+['']*3)[:3]):label.setText(line)

    def text(self):return self._text
