"""Four aligned fields in the model selector's popup."""
from PySide6.QtCore import Qt,QRect
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication,QStyle,QStyleOptionViewItem
from .centered_combo import ComboItemDelegate

MODEL_COLUMNS_ROLE=Qt.ItemDataRole.UserRole+1


class ModelItemDelegate(ComboItemDelegate):
    def paint(self,painter,option,index):
        fields=index.data(MODEL_COLUMNS_ROLE)
        if not fields or len(fields)!=4:
            return super().paint(painter,option,index)
        item=QStyleOptionViewItem(option);self.initStyleOption(item,index);item.text=''
        style=item.widget.style() if item.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem,item,painter,item.widget)
        rect=item.rect.adjusted(10,0,-10,0)
        boundaries=[rect.left()+round(rect.width()*fraction) for fraction in (0,.24,.40,.68,1)]
        painter.save()
        role=QPalette.ColorRole.HighlightedText if item.state & QStyle.StateFlag.State_Selected else QPalette.ColorRole.Text
        painter.setPen(item.palette.color(role));painter.setFont(item.font)
        for text,left,right in zip(fields,boundaries,boundaries[1:]):
            cell=QRect(left,rect.top(),max(0,right-left),rect.height()).adjusted(4,0,-4,0)
            value=item.fontMetrics.elidedText(str(text),Qt.TextElideMode.ElideRight,max(0,cell.width()))
            painter.drawText(cell,Qt.AlignmentFlag.AlignCenter,value)
        painter.restore()
