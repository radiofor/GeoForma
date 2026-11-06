"""Shared, lightweight category buttons for the selected label."""
from PySide6.QtCore import Qt,QSize,QSignalBlocker,Signal,QEvent,QTimer
from PySide6.QtWidgets import (QTableWidget,QTableWidgetItem,QAbstractItemView,QHeaderView,
    QPushButton,QStyle,QStyleOptionButton,QStyledItemDelegate)
from shiboken6 import isValid
from ..class_colors import class_color
from .color_controls import color_icon

ID_ROLE=Qt.ItemDataRole.UserRole
ACTIVE_ROLE=Qt.ItemDataRole.UserRole+1


class CategoryButtonDelegate(QStyledItemDelegate):
    def __init__(self,view):
        super().__init__(view);self.prototype=QPushButton(view);self.prototype.setCheckable(True);self.prototype.hide()

    def sizeHint(self,option,index):return QSize(0,self.parent().row_height)

    def paint(self,painter,option,index):
        button=QStyleOptionButton();self.prototype.initStyleOption(button)
        button.rect=option.rect.adjusted(2,2,-2,-2)
        button.state &= ~(QStyle.StateFlag.State_On|QStyle.StateFlag.State_Off|QStyle.StateFlag.State_HasFocus|QStyle.StateFlag.State_MouseOver|QStyle.StateFlag.State_Sunken)
        button.state |= QStyle.StateFlag.State_On if index.data(ACTIVE_ROLE) else QStyle.StateFlag.State_Off
        if option.state & QStyle.StateFlag.State_Enabled:button.state |= QStyle.StateFlag.State_Enabled
        else:button.state &= ~QStyle.StateFlag.State_Enabled
        if option.state & QStyle.StateFlag.State_MouseOver:button.state |= QStyle.StateFlag.State_MouseOver
        button.icon=index.data(Qt.ItemDataRole.DecorationRole);button.iconSize=QSize(16,12)
        button.text=option.fontMetrics.elidedText(index.data(Qt.ItemDataRole.DisplayRole) or '',Qt.TextElideMode.ElideRight,max(0,button.rect.width()-44))
        painter.save();painter.setFont(option.font)
        self.prototype.style().drawControl(QStyle.ControlElement.CE_PushButton,button,painter,self.prototype)
        painter.restore()


class CategoryButtons(QTableWidget):
    requested=Signal(object)
    nameHovered=Signal(str)
    row_height=38
    max_visible_rows=3
    def __init__(self,parent=None):
        super().__init__(0,6,parent);self.records=();self.items={};self.active=None;self._layout_pending=False;self._hover_name='';self._columns=0
        self.setAccessibleName('标注类别');self.setStyleSheet('QTableWidget{background:transparent;border:0;outline:0;} QTableWidget::item{padding:0;margin:0;border:0;}')
        self.horizontalHeader().hide();self.verticalHeader().hide();self.setShowGrid(False)
        self.horizontalHeader().setMinimumSectionSize(0);self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed);self.verticalHeader().setDefaultSectionSize(self.row_height)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection);self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setMouseTracking(True);self.setItemDelegate(CategoryButtonDelegate(self))
        self._viewport=self.viewport();self._viewport.installEventFilter(self)
        self.itemClicked.connect(lambda item:self.requested.emit(item.data(ID_ROLE)))
        self.itemActivated.connect(lambda item:self.requested.emit(item.data(ID_ROLE)))
        self.setFixedHeight(0)

    def resizeEvent(self,event):
        super().resizeEvent(event);self._schedule_layout()

    def showEvent(self,event):
        super().showEvent(event);self._schedule_layout()

    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type()==QEvent.Type.FontChange and hasattr(self,'records'):
            self.row_height=max(38,self.fontMetrics().height()+16)
            self.verticalHeader().setDefaultSectionSize(self.row_height);self._schedule_layout()

    def _column_count(self):
        count=len(self.records)
        if not count:return 0
        # Reserve a possible scrollbar to avoid changing columns when it appears.
        capacity=max(1,min(3,(self.width()-self.verticalScrollBar().sizeHint().width())//90))
        if count<=capacity:return count
        for columns in range(2,capacity+1):
            if count<=2*columns and count%columns==0:return columns
        return capacity

    def _schedule_layout(self):
        if not self._layout_pending:
            self._layout_pending=True;QTimer.singleShot(0,self,self._relayout)

    def _relayout(self):
        self._layout_pending=False;columns=self._column_count();count=len(self.records)
        rows=(count+columns-1)//columns if columns else 0
        height=min(rows,self.max_visible_rows)*self.row_height
        if self.height()!=height:self.setFixedHeight(height)
        if columns==self._columns and self.rowCount()==rows:return
        active_item=self.items.get(self.active);scroll=self.verticalScrollBar().value()
        self._columns=columns
        with QSignalBlocker(self):
            for item in self.items.values():
                if item.tableWidget() is self:self.takeItem(item.row(),item.column())
            self.clearSpans();self.setRowCount(rows)
            for row in range(rows):
                number=min(columns,count-row*columns);span=6//number
                for position in range(number):
                    item=self.items[self.records[row*columns+position][0]];column=position*span
                    self.setSpan(row,column,1,span);self.setItem(row,column,item)
        if active_item is not None:QTimer.singleShot(0,self,self._reveal_active)
        else:self.verticalScrollBar().setValue(scroll)

    def _reveal_active(self):
        item=self.items.get(self.active)
        if item is not None and item.tableWidget() is self:self.scrollToItem(item,QAbstractItemView.ScrollHint.EnsureVisible)

    def eventFilter(self,obj,event):
        viewport=getattr(self,'_viewport',None)
        if isValid(self) and viewport is not None and isValid(viewport) and obj is viewport:
            if event.type()==QEvent.Type.Resize:self._schedule_layout()
            elif event.type() in (QEvent.Type.MouseMove,QEvent.Type.Leave):
                item=self.itemAt(event.position().toPoint()) if event.type()==QEvent.Type.MouseMove else None
                name=item.text() if item and self.fontMetrics().horizontalAdvance(item.text())>max(0,self.visualItemRect(item).width()-44) else ''
                if name!=self._hover_name:self._hover_name=name;self.nameHovered.emit(name)
        return super().eventFilter(obj,event)

    def sync(self,categories,active,enabled):
        values=tuple((c['id'],c['name'],class_color(c)) for c in categories)
        if values!=self.records:
            with QSignalBlocker(self):
                wanted={identifier for identifier,_,_ in values}
                for identifier in tuple(self.items):
                    if identifier not in wanted:
                        item=self.items.pop(identifier)
                        if item.tableWidget() is self:self.takeItem(item.row(),item.column())
                for index,(identifier,name,color) in enumerate(values):
                    item=self.items.get(identifier)
                    if item is None:
                        item=QTableWidgetItem();item.setData(ID_ROLE,identifier);self.items[identifier]=item
                    if item.text()!=name:item.setText(name);item.setToolTip(name);item.setData(Qt.ItemDataRole.AccessibleTextRole,name)
                    if item.data(Qt.ItemDataRole.UserRole+2)!=color:
                        item.setData(Qt.ItemDataRole.UserRole+2,color);item.setIcon(color_icon(color))
                previous_ids=tuple(record[0] for record in self.records);self.records=values
                if previous_ids!=tuple(record[0] for record in values):self._columns=-1
                self._relayout()
        if active!=self.active:
            for identifier in (self.active,active):
                item=self.items.get(identifier)
                if item:item.setData(ACTIVE_ROLE,identifier==active)
            self.active=active
            item=self.items.get(active)
            if item is not None:self.scrollToItem(item,QAbstractItemView.ScrollHint.EnsureVisible)
        if self.isEnabled()!=enabled:self.setEnabled(enabled)
