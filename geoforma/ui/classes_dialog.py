"""Staged category editing with aligned, directly editable table cells."""
from PySide6.QtCore import QEvent,Qt,QSignalBlocker
from PySide6.QtWidgets import (QAbstractItemView,QDialog,QHeaderView,QHBoxLayout,QLineEdit,
    QPushButton,QSpinBox,QStatusBar,QTableWidget,QTableWidgetItem,QVBoxLayout,QWidget)
from ..classes import validate_classes,class_value,next_class_value
from ..class_colors import allocate_color,class_color,normalize_color
from .color_controls import ColorSwatch,choose_color
from .modal import dialog_buttons
from .text import ui_text


class ClassesDialog(QDialog):
    def __init__(self,classes,next_id,used,current=None,parent=None):
        super().__init__(parent);self.setWindowTitle(ui_text('dialogs.__init__.002'));self.resize(480,330)
        self.classes=[dict(c) for c in classes];self.next_id=next_id;self.used=used;self._rebuilding=False
        self.name_inputs={};self.swatches={};self.value_inputs={}
        layout=QVBoxLayout(self);self.list=QTableWidget(0,3)
        self.list.setHorizontalHeaderLabels(['名称',ui_text('classes.value'),'符号'])
        self.list.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        header=self.list.horizontalHeader();header.setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        for column,width in ((1,120),(2,72)):
            header.setSectionResizeMode(column,QHeaderView.ResizeMode.Fixed);self.list.setColumnWidth(column,width)
        self.list.verticalHeader().hide();self.list.setShowGrid(False)
        self.list.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);layout.addWidget(self.list,1)
        row=QHBoxLayout();self.add_button=QPushButton(ui_text('dialogs.__init__.004'))
        self.delete_button=QPushButton(ui_text('action.delete'));self.delete_button.setProperty('role','danger')
        row.addWidget(self.add_button);row.addWidget(self.delete_button);layout.addLayout(row)
        self.status=QStatusBar(self);self.status.setSizeGripEnabled(False)
        self.status.setStyleSheet('QStatusBar{background:transparent;border:0;}');layout.addWidget(self.status)
        self.add_button.clicked.connect(self.add);self.delete_button.clicked.connect(self.remove)
        self.list.currentCellChanged.connect(self.select);layout.addWidget(dialog_buttons(self));self.refresh(current)

    def eventFilter(self,obj,event):
        if event.type()==QEvent.Type.FocusIn:
            identifier=obj.property('classId')
            if identifier is not None:
                row=next((i for i,c in enumerate(self.classes) if c['id']==identifier),-1)
                if row>=0 and self.list.currentRow()!=row:self.list.setCurrentCell(row,0)
        return super().eventFilter(obj,event)

    def _track_focus(self,widget,identifier):
        widget.setProperty('classId',identifier);widget.installEventFilter(self)

    def refresh(self,current=None):
        self._rebuilding=True
        try:self._rebuild_rows(current)
        finally:self._rebuilding=False
        self.select()

    def _rebuild_rows(self,current):
        with QSignalBlocker(self.list):
            self.list.setRowCount(0);self.name_inputs={};self.swatches={};self.value_inputs={}
            for row,category in enumerate(self.classes):
                identifier=category['id'];self.list.insertRow(row);self.list.setRowHeight(row,38)
                for column in range(3):
                    item=QTableWidgetItem();item.setData(Qt.ItemDataRole.UserRole,identifier)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter);self.list.setItem(row,column,item)
                name=QLineEdit(category['name']);name.setMaxLength(2**31-1);name.setMinimumWidth(0)
                name.setAlignment(Qt.AlignmentFlag.AlignCenter);name.setAccessibleName(ui_text('dialogs.__init__.003'))
                name.setCursorPosition(0);self._track_focus(name,identifier)
                name.editingFinished.connect(self.commit_names);self.list.setCellWidget(row,0,name);self.name_inputs[identifier]=name
                spin=QSpinBox();spin.setRange(1,65534);spin.setValue(class_value(category));spin.setKeyboardTracking(False)
                spin.setStyleSheet('QSpinBox{padding-left:22px;padding-right:4px;}')
                spin.setAlignment(Qt.AlignmentFlag.AlignCenter);spin.setAccessibleName(ui_text('classes.value_accessible').format(category['name']))
                spin.setToolTip(ui_text('classes.value_hint'));spin.valueChanged.connect(lambda value,identifier=identifier:self.change_value(identifier,value))
                self._track_focus(spin,identifier);self._track_focus(spin.lineEdit(),identifier)
                self.list.setCellWidget(row,1,spin);self.value_inputs[identifier]=spin
                wrapper=QWidget();box=QHBoxLayout(wrapper);box.setContentsMargins(0,0,0,0)
                swatch=ColorSwatch(class_color(category),category['name'],wrapper);self._track_focus(swatch,identifier)
                swatch.clicked.connect(lambda checked=False,identifier=identifier:self.change_color(identifier))
                box.addWidget(swatch,0,Qt.AlignmentFlag.AlignCenter);self.list.setCellWidget(row,2,wrapper);self.swatches[identifier]=swatch
            index=next((i for i,c in enumerate(self.classes) if c['id']==current),0)
            if self.classes:self.list.setCurrentCell(index,0)

    def select(self,*args):
        row=self.list.currentRow();item=self.classes[row] if 0<=row<len(self.classes) else None
        self.delete_button.setEnabled(item is not None and item['id'] not in self.used)

    def validate(self,items):
        try:validate_classes(items);self.status.clearMessage();return True
        except ValueError as error:self.status.showMessage(str(error));return False

    def commit_names(self):
        if self._rebuilding:return True
        items=[dict(c,name=self.name_inputs[c['id']].text().strip()) for c in self.classes]
        if not self.validate(items):return False
        self.classes=items
        for category in items:
            identifier=category['id'];name=category['name']
            self.value_inputs[identifier].setAccessibleName(ui_text('classes.value_accessible').format(name))
            self.swatches[identifier].setAccessibleName(ui_text('classes.color_accessible').format(name))
        return True

    def add(self):
        if not self.commit_names():return
        if self.next_id>65534:self.status.showMessage(ui_text('dialogs.add.021'));return
        value=next_class_value(self.classes)
        if value>65534:self.status.showMessage(ui_text('classes.values_exhausted'));return
        names={c['name'].casefold() for c in self.classes};suffix=self.next_id;name=f'类别 {suffix}'
        while name.casefold() in names:suffix+=1;name=f'类别 {suffix}'
        item={'id':self.next_id,'name':name,'value':value,'color':allocate_color(self.next_id,self.classes)}
        self.classes.append(item);self.next_id+=1;self.refresh(item['id'])
        self.name_inputs[item['id']].setFocus();self.name_inputs[item['id']].selectAll()

    def change_value(self,identifier,value):
        if self._rebuilding:return
        row=next(i for i,c in enumerate(self.classes) if c['id']==identifier)
        items=[dict(c) for c in self.classes];items[row]['value']=value
        if not self.validate(items):
            with QSignalBlocker(self.value_inputs[identifier]):self.value_inputs[identifier].setValue(class_value(self.classes[row]))
            return
        self.classes=items

    def change_color(self,identifier):
        row=next(i for i,c in enumerate(self.classes) if c['id']==identifier);self.list.setCurrentCell(row,2)
        category=self.classes[row];color=choose_color(class_color(category),self.name_inputs[identifier].text().strip(),self)
        if color is not None:category['color']=normalize_color(color);self.swatches[identifier].set_color(category['color'])

    def remove(self):
        row=self.list.currentRow()
        if row>=0 and self.classes[row]['id'] not in self.used:
            items=[dict(c,name=self.name_inputs[c['id']].text().strip()) for i,c in enumerate(self.classes) if i!=row]
            if not self.validate(items):return
            self.classes=items;self.refresh()

    def value(self):
        row=self.list.currentRow()
        return self.classes,self.next_id,self.classes[row]['id'] if 0<=row<len(self.classes) else None

    def accept(self):
        for control in self.value_inputs.values():control.interpretText()
        if self.commit_names():super().accept()
