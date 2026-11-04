"""Incremental presentation of label rows; never owns annotation geometry."""
from .text import ui_text
from dataclasses import dataclass
from PySide6.QtCore import Qt,QSignalBlocker,QEvent
from PySide6.QtWidgets import QTableWidget,QTableWidgetItem,QAbstractItemView,QHeaderView,QScrollBar,QSizePolicy,QWidget,QHBoxLayout


class CategoryCell(QWidget):
    """Center the category field with compact clearance between rows."""
    def __init__(self,parent=None):
        super().__init__(parent)
        from .centered_combo import CenteredComboBox
        self.combo=CenteredComboBox(self);self.combo.setMinimumWidth(0)
        self.combo.expand_popup=True
        self.combo.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
        self.combo.setStyleSheet('QComboBox{padding:2px 6px;min-height:18px;}')
        layout=QHBoxLayout(self);layout.setContentsMargins(6,2,6,2);layout.setSpacing(0)
        layout.addWidget(self.combo,1,Qt.AlignmentFlag.AlignVCenter)
        self.sync_metrics()

    def sync_metrics(self):self.combo.setFixedHeight(max(26,self.fontMetrics().height()+8))


class LabelTable(QTableWidget):
    """Keep the header full-width; the vertical scrollbar lives inside the body."""
    def __init__(self,parent=None):
        super().__init__(0,3,parent)
        # Index widgets otherwise inherit the global item padding as a second
        # inset, which shifts short fields down inside compact rows.
        self.setStyleSheet('QTableWidget::item{padding:0px;}')
        # Give editable categories the flexible space; numbers and short
        # statuses keep stable widths as the sidebar or row content changes.
        header=self.horizontalHeader()
        header.setSectionResizeMode(0,QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2,QHeaderView.ResizeMode.Fixed)
        self.verticalHeader().sectionCountChanged.connect(lambda old,new:self.sync_serial_width(new))
        from .label_status import LabelStatusDelegate
        self.setItemDelegateForColumn(2,LabelStatusDelegate(self))
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body_scrollbar=QScrollBar(Qt.Orientation.Vertical,self.viewport())
        self.body_scrollbar.hide()
        native=self.verticalScrollBar()
        native.rangeChanged.connect(self._sync_scrollbar)
        native.valueChanged.connect(self.body_scrollbar.setValue)
        self.body_scrollbar.valueChanged.connect(native.setValue)
        self.sync_row_metrics()

    def category_combo(self,row):
        cell=self.cellWidget(row,1)
        return cell.combo if isinstance(cell,CategoryCell) else None

    def sync_row_metrics(self):
        height=max(32,self.fontMetrics().height()+14)
        self.verticalHeader().setMinimumSectionSize(height);self.verticalHeader().setDefaultSectionSize(height)
        for row in range(self.rowCount()):
            cell=self.cellWidget(row,1)
            if isinstance(cell,CategoryCell):cell.sync_metrics()
        self.sync_serial_width(self.rowCount())
        self.sync_status_width()

    def serial_column_width(self,count):return max(48,self.fontMetrics().horizontalAdvance(str(max(1,count)))+16)

    def sync_serial_width(self,count):
        width=self.serial_column_width(count)
        if self.columnWidth(0)!=width:self.setColumnWidth(0,width)

    def sync_status_width(self):
        if not hasattr(self,'body_scrollbar'):return
        from .status_style import status_column_width
        width=status_column_width(self.fontMetrics(),self.body_scrollbar.sizeHint().width())
        if self.columnWidth(2)!=width:self.setColumnWidth(2,width)

    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type()==QEvent.Type.FontChange:self.sync_row_metrics()

    def _sync_scrollbar(self,*args):
        if not hasattr(self,'body_scrollbar'):return
        native=self.verticalScrollBar();bar=self.body_scrollbar
        blocker=QSignalBlocker(bar)
        bar.setRange(native.minimum(),native.maximum())
        bar.setPageStep(native.pageStep());bar.setSingleStep(native.singleStep());bar.setValue(native.value())
        del blocker
        width=bar.sizeHint().width();viewport=self.viewport()
        bar.setGeometry(max(0,viewport.width()-width),0,width,viewport.height())
        bar.setVisible(native.maximum()>native.minimum());bar.raise_()

    def updateGeometries(self):
        super().updateGeometries();self._sync_scrollbar()


@dataclass(frozen=True)
class LabelRow:
    identifier:str
    title:str
    status:str
    edge:bool=False
    selected:bool=False
    class_id:int|None=None


class LabelTablePresenter:
    def __init__(self,table):self.table=table;self.rows=();table.setColumnCount(3);self.categories=();self.category_callback=None;self.categories_changed=False

    def set_categories(self,categories,callback):
        values=tuple((c['id'],c['name']) for c in categories)
        self.categories_changed=values!=self.categories;self.categories=values;self.category_callback=callback

    def category_editor(self,row,index):
        if self.category_callback is None:return
        combo=self.table.category_combo(index)
        if combo is None or combo.property('labelId')!=row.identifier:
            cell=CategoryCell();combo=cell.combo
            combo.setProperty('labelId',row.identifier);combo.setAccessibleName(ui_text('labels.category_accessible').format(row.identifier))
            combo.currentIndexChanged.connect(lambda _,c=combo:self.category_callback(c.property('labelId'),c.currentData()))
            self.table.setCellWidget(index,1,cell)
        blocked=QSignalBlocker(combo)
        values=tuple((combo.itemData(i),combo.itemText(i)) for i in range(combo.count()))
        if values!=self.categories:
            combo.clear()
            for identifier,name in self.categories:combo.addItem(name,identifier)
        combo.setCurrentIndex(combo.findData(row.class_id));combo.setPlaceholderText(row.title)
        del blocked

    def reveal(self,identifier):
        for row in range(self.table.rowCount()):
            item=self.table.item(row,0)
            if item.data(Qt.ItemDataRole.UserRole)==identifier:
                self.table.scrollToItem(item,QAbstractItemView.ScrollHint.EnsureVisible)
                return

    def sync(self,rows):
        rows=tuple(rows)
        if rows==self.rows and not self.categories_changed:return
        table=self.table;structural=tuple(r.identifier for r in rows)!=tuple(r.identifier for r in self.rows)
        blocker=QSignalBlocker(table);scroll=table.verticalScrollBar().value()
        try:
            if structural:
                wanted={r.identifier for r in rows}
                for i in range(table.rowCount()-1,-1,-1):
                    if table.item(i,0).data(Qt.ItemDataRole.UserRole) not in wanted:table.removeRow(i)
            for i,row in enumerate(rows):
                if not structural and row==self.rows[i] and not self.categories_changed:continue
                if i>=table.rowCount() or table.item(i,0).data(Qt.ItemDataRole.UserRole)!=row.identifier:
                    existing=next((j for j in range(i,table.rowCount()) if table.item(j,0).data(Qt.ItemDataRole.UserRole)==row.identifier),None)
                    if existing is None:
                        table.insertRow(i)
                        for c in range(3):table.setItem(i,c,QTableWidgetItem())
                    else:
                        cells=[table.takeItem(existing,c) for c in range(3)];table.removeRow(existing);table.insertRow(i)
                        for c,item in enumerate(cells):table.setItem(i,c,item)
                serial,first,state=(table.item(i,c) for c in range(3))
                for item in (serial,first,state):
                    if item.textAlignment()!=Qt.AlignmentFlag.AlignCenter:item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    if item.data(Qt.ItemDataRole.UserRole)!=row.identifier:item.setData(Qt.ItemDataRole.UserRole,row.identifier);item.setToolTip(row.identifier)
                if serial.text()!=str(i+1):serial.setText(str(i+1))
                if first.text()!=row.title:first.setText(row.title)
                if first.data(Qt.ItemDataRole.UserRole)!=row.identifier:first.setData(Qt.ItemDataRole.UserRole,row.identifier);first.setToolTip(row.identifier)
                if state.text()!=row.status:state.setText(row.status)
                self.category_editor(row,i)
                tip=ui_text('label_table.sync.001') if row.edge else ''
                if state.toolTip()!=tip:state.setToolTip(tip)
                for item in (serial,first,state):
                    if item.isSelected()!=row.selected:item.setSelected(row.selected)
            self.rows=rows
            self.categories_changed=False
        finally:
            if structural:table.verticalScrollBar().setValue(scroll)
            del blocker
