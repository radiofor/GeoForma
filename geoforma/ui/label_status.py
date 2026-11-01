"""Centered status captions with distinct colors, painted inside table cells."""
from PySide6.QtCore import Qt,QRectF
from PySide6.QtGui import QColor,QPainter,QPen
from PySide6.QtWidgets import QApplication,QStyledItemDelegate,QStyleOptionViewItem,QStyle
from .status_style import (STYLES,status_badge_width,BADGE_PADDING_Y,
    BADGE_TEXT_INSET,BADGE_MARGIN_X,BADGE_MARGIN_Y,BADGE_RADIUS)


def status_layout(cell,metrics,text):
    """Center the badge in its column and its caption within equal padding."""
    cell=QRectF(cell)
    width=max(0,min(cell.width()-2*BADGE_MARGIN_X,status_badge_width(metrics,text)))
    height=max(0,min(cell.height()-2*BADGE_MARGIN_Y,metrics.height()+2*BADGE_PADDING_Y))
    badge=QRectF(cell.center().x()-width/2,cell.center().y()-height/2,width,height)
    padding=min(BADGE_TEXT_INSET,width/2)
    caption=badge.adjusted(padding,0,-padding,0)
    return badge,caption


class LabelStatusDelegate(QStyledItemDelegate):
    def paint(self,painter,option,index):
        text=index.data(Qt.ItemDataRole.DisplayRole) or '';style=STYLES.get(text)
        if style is None:super().paint(painter,option,index);return
        opt=QStyleOptionViewItem(option);self.initStyleOption(opt,index);opt.text=''
        painter.save();painter.setClipRect(opt.rect,Qt.ClipOperation.IntersectClip)
        widget_style=opt.widget.style() if opt.widget else QApplication.style()
        widget_style.drawControl(QStyle.ControlElement.CE_ItemViewItem,opt,painter,opt.widget)
        ink,background,border=style
        rect,label=status_layout(opt.rect,opt.fontMetrics,text)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(border),1));painter.setBrush(QColor(background));painter.drawRoundedRect(rect,BADGE_RADIUS,BADGE_RADIUS)
        if label.width()>0 and rect.height()>=16:
            painter.setPen(QColor(ink));painter.setFont(opt.font)
            painter.drawText(label,Qt.AlignmentFlag.AlignCenter,
                             opt.fontMetrics.elidedText(text,Qt.TextElideMode.ElideRight,max(0,int(label.width()))))
        painter.restore()
