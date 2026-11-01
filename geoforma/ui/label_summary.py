"""Equal-width count buttons with optional, mutually exclusive filtering."""
from PySide6.QtCore import Qt,QRectF,QSize,Signal
from PySide6.QtGui import QColor,QFont,QFontMetrics,QPainter,QPen
from PySide6.QtWidgets import QWidget,QPushButton,QSizePolicy,QHBoxLayout
from .status_style import SAVED_COLORS,REVIEW_COLORS,BADGE_RADIUS
from .text import ui_text


class CountFilterButton(QPushButton):
    def __init__(self,caption,kind,parent):
        super().__init__(caption,parent);self.caption=caption;self.kind=kind;self.count=0;self.ready=True
        self.setCheckable(True);self.setFixedHeight(32);self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)

    def sizeHint(self):return QSize(0,32)
    def minimumSizeHint(self):return QSize(0,32)

    def set_count(self,count,ready):
        changed=(self.count,self.ready)!=(count,ready);self.count=count;self.ready=ready
        self.setAccessibleName(f'{self.caption} {count}' if ready else self.caption+'：'+ui_text('labels.summary_pending'))
        if changed:self.update()

    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        ink,background,border=SAVED_COLORS if self.kind=='saved' else REVIEW_COLORS
        if self.isChecked():background=border=ink;ink='#ffffff'
        rect=QRectF(self.rect()).adjusted(.75,.75,-.75,-.75)
        painter.setPen(QPen(QColor(border),1.5 if self.isChecked() else 1));painter.setBrush(QColor(background));painter.drawRoundedRect(rect,BADGE_RADIUS,BADGE_RADIUS)
        painter.setOpacity(1. if self.isEnabled() else .5)
        font=QFont(self.font());font.setWeight(QFont.Weight.DemiBold);painter.setFont(font);painter.setPen(QColor(ink))
        number=f'{self.count:,}' if self.ready else '…';metrics=QFontMetrics(font)
        content=rect.adjusted(10,0,-10,0);number_width=metrics.horizontalAdvance(number)
        painter.drawText(content,Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter,metrics.elidedText(number,Qt.TextElideMode.ElideRight,max(0,int(content.width()))))
        content.setRight(content.right()-number_width-6);painter.setFont(self.font())
        painter.drawText(content,Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,self.fontMetrics().elidedText(self.caption,Qt.TextElideMode.ElideRight,max(0,int(content.width()))))


class LabelSummary(QWidget):
    currentIndexChanged=Signal(int)

    def __init__(self,parent=None):
        super().__init__(parent);self.saved=0;self.candidates=0;self.ready=True;self._filter=0
        self.setFixedHeight(32);self.setMinimumWidth(0);self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
        row=QHBoxLayout(self);row.setContentsMargins(0,0,0,0);row.setSpacing(6)
        self.saved_button=CountFilterButton(ui_text('status.confirmed'),'saved',self);self.candidate_button=CountFilterButton(ui_text('status.candidate'),'candidate',self)
        for index,button in enumerate((self.saved_button,self.candidate_button),1):
            row.addWidget(button,1);button.clicked.connect(lambda checked=False,i=index:self.setCurrentIndex(0 if self._filter==i else i))
        self.set_counts(0,0)

    def sizeHint(self):return QSize(0,32)
    def minimumSizeHint(self):return QSize(0,32)
    def currentIndex(self):return self._filter

    def setCurrentIndex(self,index):
        if index not in (0,1,2) or index==self._filter:return
        self._filter=index;self.saved_button.setChecked(index==1);self.candidate_button.setChecked(index==2)
        self.currentIndexChanged.emit(index)

    def set_counts(self,saved,candidates=None,ready=True):
        self.saved=saved;self.candidates=candidates or 0;self.ready=ready
        self.saved_button.set_count(saved,ready);self.candidate_button.set_count(self.candidates,ready);self.setAccessibleName(self.text())

    def text(self):return ui_text('labels.summary_counts').format(self.saved,self.candidates) if self.ready else ui_text('labels.summary_pending')
