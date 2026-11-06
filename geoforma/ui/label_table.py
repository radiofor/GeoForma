"""Incremental presentation of label rows; never owns annotation geometry."""
from .text import ui_text
from dataclasses import dataclass
from PySide6.QtCore import Qt,QSignalBlocker,QEvent
from PySide6.QtWidgets import QTableWidget,QTableWidgetItem,QAbstractItemView,QHeaderView,QScrollBar


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

    def sync_row_metrics(self):
        height=max(32,self.fontMetrics().height()+14)
        self.verticalHeader().setMinimumSectionSize(height);self.verticalHeader().setDefaultSectionSize(height)
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
    def __init__(self,table):
        self.table=table;self.rows=();table.setColumnCount(3)
        if isinstance(table,LabelTable):
            from .list_transition import LabelListTransition
            self.transition=LabelListTransition(table)

    def reveal(self,identifier):
        for row in range(self.table.rowCount()):
            item=self.table.item(row,0)
            if item.data(Qt.ItemDataRole.UserRole)==identifier:
                self.table.scrollToItem(item,QAbstractItemView.ScrollHint.EnsureVisible)
                return

    def sync(self,rows):
        rows=tuple(rows)
        if rows==self.rows:return
        table=self.table;structural=tuple(r.identifier for r in rows)!=tuple(r.identifier for r in self.rows)
        blocker=QSignalBlocker(table);scroll=table.verticalScrollBar().value()
        # Different images have disjoint IDs; reuse existing item objects.
        rebind=structural and bool(rows) and bool(self.rows) and not ({r.identifier for r in rows}&{r.identifier for r in self.rows})
        viewport=table.viewport();updates=viewport.updatesEnabled()
        if structural and updates:viewport.setUpdatesEnabled(False)
        try:
            if rebind:
                table.setRowCount(len(rows))
                for i in range(table.rowCount()):
                    for c in range(3):
                        if table.item(i,c) is None:table.setItem(i,c,QTableWidgetItem())
            elif structural:
                wanted={r.identifier for r in rows}
                for i in range(table.rowCount()-1,-1,-1):
                    if table.item(i,0).data(Qt.ItemDataRole.UserRole) not in wanted:table.removeRow(i)
            for i,row in enumerate(rows):
                if not structural and row==self.rows[i]:continue
                if not rebind and (i>=table.rowCount() or table.item(i,0).data(Qt.ItemDataRole.UserRole)!=row.identifier):
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
                if first.toolTip()!=row.title:first.setToolTip(row.title)
                first.setData(Qt.ItemDataRole.AccessibleTextRole,row.title)
                first.setData(Qt.ItemDataRole.AccessibleDescriptionRole,ui_text('labels.category_accessible').format(row.identifier))
                if state.text()!=row.status:state.setText(row.status)
                tip=ui_text('label_table.sync.001') if row.edge else ''
                if state.toolTip()!=tip:state.setToolTip(tip)
                for item in (serial,first,state):
                    if item.isSelected()!=row.selected:item.setSelected(row.selected)
            self.rows=rows
        finally:
            if structural:table.verticalScrollBar().setValue(scroll)
            del blocker
            if structural and updates:viewport.setUpdatesEnabled(True);viewport.update()
