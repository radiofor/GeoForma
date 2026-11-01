"""Stage reference-type changes without touching raster files or live display state."""
from PySide6.QtCore import Qt,QSize,QSignalBlocker
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QTableWidget,QTableWidgetItem,
    QHeaderView,QAbstractItemView,QWidget,QToolButton,QDialogButtonBox,QStyledItemDelegate,QLineEdit,QAbstractItemDelegate)
from ..reference_images import reference_group_name
from ..tool_icons import icon
from .controls import ElidedLabel


class ReferenceTypeDelegate(QStyledItemDelegate):
    def createEditor(self,parent,option,index):
        editor=super().createEditor(parent,option,index)
        if isinstance(editor,QLineEdit):editor.setAlignment(Qt.AlignmentFlag.AlignCenter);editor.setAccessibleName('参考类型名称')
        return editor


class ReferenceManagerDialog(QDialog):
    def __init__(self,references,parent=None):
        super().__init__(parent);self.setWindowTitle('参考影像管理');self.resize(390,330)
        self.references=[dict(record) for record in references]
        self._pairs=list(zip(references,self.references));self.groups=[]
        layout=QVBoxLayout(self)
        self.table=QTableWidget(0,3);self.table.setHorizontalHeaderLabels(['参考类型','影像数',''])
        self.table.setStyleSheet('QTableWidget::item:selected{background:#e1f3ef;color:#174b51;}')
        self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeMode.Fixed);self.table.setColumnWidth(2,40)
        self.table.setItemDelegateForColumn(0,ReferenceTypeDelegate(self.table))
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.verticalHeader().hide();self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked|QAbstractItemView.EditTrigger.EditKeyPressed|QAbstractItemView.EditTrigger.SelectedClicked);layout.addWidget(self.table,1)
        self.message=ElidedLabel();self.message.setFixedHeight(22);self.message.setProperty('role','muted');layout.addWidget(self.message)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('确定');buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
        self.table.itemChanged.connect(self.rename)
        self.refresh()

    def refresh(self,current=None):
        groups={}
        for record in self.references:
            key=record['group'].casefold()
            if key not in groups:groups[key]=[record['group'],0]
            groups[key][1]+=1
        selected=self.table.currentRow();scroll=self.table.verticalScrollBar().value()
        self.groups=list(groups.values());blocker=QSignalBlocker(self.table);self.table.setRowCount(0);self.table.setRowCount(len(self.groups))
        for row,(name,count) in enumerate(self.groups):
            for column,value in enumerate((name,str(count),'')):
                item=QTableWidgetItem(value);item.setTextAlignment(Qt.AlignmentFlag.AlignCenter);item.setData(Qt.ItemDataRole.UserRole,name)
                if column:item.setFlags(item.flags()&~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row,column,item)
            target=self.table.item(row,0);holder=QWidget();buttons=QHBoxLayout(holder);buttons.setContentsMargins(0,0,0,0)
            remove=QToolButton(holder);remove.setIcon(icon('delete','#c34f60'));remove.setIconSize(QSize(17,17));remove.setFixedSize(28,28);remove.setAutoRaise(True)
            remove.setStyleSheet('QToolButton{padding:0;}')
            remove.setProperty('role','danger');remove.setAccessibleName('移除'+name+'参考类型')
            remove.clicked.connect(lambda checked=False,item=target:self.remove(item))
            buttons.addWidget(remove,0,Qt.AlignmentFlag.AlignCenter);self.table.setCellWidget(row,2,holder);self.table.setRowHeight(row,34)
        if self.groups:self.table.selectRow(next((i for i,(name,_) in enumerate(self.groups) if name==current),max(0,min(selected,len(self.groups)-1))))
        self.table.verticalScrollBar().setValue(scroll);del blocker;self.message.setText('')

    def rename(self,item=None):
        if item is not None and item.column()!=0:return True
        row=item.row() if item is not None else self.table.currentRow()
        if not 0<=row<len(self.groups):return False
        item=self.table.item(row,0);old=self.groups[row][0]
        if item.text()==old:self.message.setText('');return True
        try:
            name=reference_group_name(item.text(),truncate=True)
            if any(group.casefold()==name.casefold() and group.casefold()!=old.casefold() for group,_ in self.groups):
                raise ValueError('参考类型名称已存在。')
        except ValueError as error:self.message.setText(str(error));return False
        for record in self.references:
            if record['group'].casefold()==old.casefold():record['group']=name
        self.groups[row][0]=name;blocker=QSignalBlocker(self.table)
        item.setText(name);item.setData(Qt.ItemDataRole.UserRole,name);del blocker
        self.table.cellWidget(row,2).findChild(QToolButton).setAccessibleName('移除'+name+'参考类型')
        self.message.setText('');return True

    def commit_editor(self):
        # Buttons can be clicked before the native cell editor loses focus.
        if self.table.state()==QAbstractItemView.State.EditingState:
            editor=next((field for field in self.table.findChildren(QLineEdit) if field.isVisible()),None)
            if editor is not None:
                self.table.commitData(editor);self.table.closeEditor(editor,QAbstractItemDelegate.EndEditHint.NoHint)

    def accept(self):
        self.commit_editor()
        # Validate every row, including failed earlier edits.
        for row in range(self.table.rowCount()):
            if not self.rename(self.table.item(row,0)):
                self.table.setCurrentCell(row,0);return
        super().accept()

    def remove(self,item=None):
        if item is None:item=self.table.item(self.table.currentRow(),0)
        if item is None:return
        self.commit_editor()
        key=item.data(Qt.ItemDataRole.UserRole).casefold();self.references=[record for record in self.references if record['group'].casefold()!=key]
        self.refresh()

    def replacement_for(self,reference):
        return next((staged for original,staged in self._pairs if original is reference and any(staged is record for record in self.references)),None)
