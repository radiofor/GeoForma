"""Stable metadata rows and counters, with a fully wrapped source directory."""
from PySide6.QtCore import Qt,QRect,QPointF,Signal
from PySide6.QtGui import QTextOption,QTextCursor,QPainter
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QSizePolicy,QPlainTextEdit
from .controls import ElidedLabel


class DirectoryReadout(QPlainTextEdit):
    heightChanged=Signal()

    def __init__(self,parent=None):
        super().__init__(parent);self.setReadOnly(True);self.setTabChangesFocus(True)
        self.setObjectName('rasterDirectory');self.setAccessibleName('文件目录');self.setMinimumWidth(0)
        self.setWordWrapMode(QTextOption.WrapMode.WrapAnywhere);self.document().setDocumentMargin(0)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet('QPlainTextEdit#rasterDirectory{border:0;border-radius:0;background:transparent;padding:0;min-height:0;color:#304c59;}')
        self.setFixedHeight(20);self.textChanged.connect(self.fit_text);self.setText('—')

    def text(self):return self.toPlainText()

    def setText(self,text):
        if text==self.text():return
        self.setPlainText(text);self.moveCursor(QTextCursor.MoveOperation.Start)

    def fit_text(self):
        rect=QRect(0,0,max(1,self.viewport().width()-4),100000)
        bounds=self.fontMetrics().boundingRect(rect,Qt.TextFlag.TextWordWrap|Qt.TextFlag.TextWrapAnywhere,self.text() or ' ')
        height=max(20,bounds.height()+4)
        if height!=self.height():self.setFixedHeight(height);self.heightChanged.emit()

    def resizeEvent(self,event):
        super().resizeEvent(event);self.fit_text()


class DistributedCaption(QLabel):
    """Align caption endpoints by spreading the gaps, keeping glyphs unscaled."""
    def paintEvent(self,event):
        text=self.text()
        if not text:return
        rect=self.contentsRect();metrics=self.fontMetrics();widths=[metrics.horizontalAdvance(char) for char in text]
        gap=max(0.,(rect.width()-sum(widths))/max(1,len(text)-1))
        painter=QPainter(self);painter.setFont(self.font());painter.setPen(self.palette().color(self.foregroundRole()))
        x=float(rect.left());baseline=rect.top()+(rect.height()-metrics.height())/2+metrics.ascent()
        for char,width in zip(text,widths):
            painter.drawText(QPointF(x,baseline),char);x+=width+gap


class RasterInfo(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self._text='';self.values=[]
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground,True)
        self.setObjectName('rasterInfo');layout=QVBoxLayout(self);layout.setContentsMargins(8,5,8,5);layout.setSpacing(2)
        for caption in ('尺寸','坐标系代码','坐标系名称','模型波段','文件目录'):
            row=QHBoxLayout();row.setSpacing(10)
            key=DistributedCaption(caption);key.setProperty('role','muted')
            font=key.font();font.setPointSizeF(8.25);key.setFont(font);key.setFixedWidth(57)
            if caption=='文件目录':
                value=DirectoryReadout();self.directory=value
                key.setFixedHeight(20);row.addWidget(key,0,Qt.AlignmentFlag.AlignTop)
            else:
                value=ElidedLabel('—');value.setFixedHeight(20);row.addWidget(key)
            row.addWidget(value,1)
            self.values.append(value);layout.addLayout(row)
        self.directory.heightChanged.connect(self.fit_directory);self.fit_directory()

    def fit_directory(self):self.setFixedHeight(98+self.directory.height())

    def setText(self,text):
        text=str(text)
        if text==self._text:return
        self._text=text;lines=self._text.splitlines();fields=[]
        for index in range(3):
            line=(lines[index] or '—') if index<len(lines) else '—'
            fields.append(line.partition('：')[2] if index and '：' in line else line)
        from ..crs_display import describe_crs
        code,name=describe_crs(fields[1] if fields[1]!='—' else '')
        for value,line in zip(self.values,[fields[0],code,name,fields[2]]):value.setText(line)
        directory=lines[3].partition('：')[2] if len(lines)>3 else '—'
        if self.directory.text()!=directory:self.directory.setText(directory)

    def text(self):return self._text
    def clear(self):self.setText('')


class PromptCounters(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self.setObjectName('promptCounters')
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground,True)
        layout=QHBoxLayout(self);layout.setContentsMargins(8,3,8,3);layout.setSpacing(8);self.values=[]
        for caption in ('正点','负点'):
            label=QLabel(caption);label.setProperty('role','muted');layout.addWidget(label)
            value=ElidedLabel('0');value.setProperty('role','counter');value.setAlignment(Qt.AlignmentFlag.AlignCenter)
            value.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed);layout.addWidget(value,1);self.values.append(value)
        self.setFixedHeight(32)

    def set_points(self,points):
        self.values[0].setText(str(sum(p[2]==1 for p in points)))
        self.values[1].setText(str(sum(p[2]==0 for p in points)))
