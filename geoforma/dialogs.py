from .ui.text import ui_text
from .ui.controls import ElidedLabel
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QFormLayout,QLabel,QDialogButtonBox,
    QSpinBox,QDoubleSpinBox,QHBoxLayout,QLineEdit,QPushButton,QFileDialog,QWidget,QListWidget,QListWidgetItem,QPlainTextEdit)
from .weights import default_checkpoint
from PySide6.QtCore import Qt,QSize,QSignalBlocker
from .classes import validate_classes,class_value,next_class_value
from .model_catalog import MODELS,model_spec
from .model_status import weight_status,memory_budget,memory_description,memory_tooltip
from .ui.reference_name import ReferenceNameDialog
from .ui.centered_combo import CenteredComboBox as QComboBox
from .ui.model_combo import ModelItemDelegate,MODEL_COLUMNS_ROLE


class ClassesDialog(QDialog):
    def __init__(self,classes,next_id,used,current=None,parent=None):
        super().__init__(parent);self.setWindowTitle(ui_text('dialogs.__init__.002'));self.resize(480,330)
        self.classes=[dict(c) for c in classes];self.next_id=next_id;self.used=used
        self.swatches={};self.value_inputs={}
        layout=QVBoxLayout(self);self.list=QListWidget();self.list.setObjectName('categoryColors')
        # Embedded row widgets need the full row height, without generic item padding.
        self.list.setStyleSheet('QListWidget#categoryColors::item{padding:0px 6px;}')
        self.list.setSpacing(3);layout.addWidget(self.list,1)
        name_row=QHBoxLayout();self.name=QLineEdit();self.name.setMaxLength(2**31-1)
        self.name.setAlignment(Qt.AlignmentFlag.AlignLeft);self.name.setMinimumWidth(0);self.name.setAccessibleName(ui_text('dialogs.__init__.003'))
        self.name.setPlaceholderText(ui_text('dialogs.__init__.003'));name_row.addWidget(self.name,1)
        self.expand_name_button=QPushButton(ui_text('classes.expand_name'));self.expand_name_button.setCheckable(True);self.expand_name_button.setAutoDefault(False)
        name_row.addWidget(self.expand_name_button);layout.addLayout(name_row)
        self.name_details=QPlainTextEdit();self.name_details.setReadOnly(True);self.name_details.setFixedHeight(96)
        self.name_details.setAccessibleName(ui_text('classes.full_name'));self.name_details.hide();layout.addWidget(self.name_details)
        self.name.textChanged.connect(self.name_details.setPlainText);self.expand_name_button.toggled.connect(self.show_full_name)
        row=QHBoxLayout();self.add_button=QPushButton(ui_text('dialogs.__init__.004'));self.rename_button=QPushButton(ui_text('dialogs.__init__.005'));self.delete_button=QPushButton(ui_text('action.delete'))
        self.delete_button.setProperty('role','danger')
        for button in [self.add_button,self.rename_button,self.delete_button]:row.addWidget(button)
        layout.addLayout(row);self.message=ElidedLabel();self.message.setFixedHeight(22);self.message.setProperty('role','muted');layout.addWidget(self.message)
        self.add_button.clicked.connect(self.add);self.rename_button.clicked.connect(self.rename);self.delete_button.clicked.connect(self.remove)
        self.list.currentRowChanged.connect(self.select);layout.addWidget(dialog_buttons(self));self.refresh(current)

    def refresh(self,current=None):
        from .class_colors import class_color
        from .ui.color_controls import category_row
        self.list.blockSignals(True);self.list.clear()
        self.swatches={};self.value_inputs={}
        for c in self.classes:
            item=QListWidgetItem();item.setData(Qt.ItemDataRole.UserRole,c['id']);item.setData(Qt.ItemDataRole.AccessibleTextRole,ui_text('classes.row_accessible').format(c['name'],class_value(c)));item.setSizeHint(QSize(240,36));self.list.addItem(item)
            row,swatch,value_input=category_row(c,class_color(c),lambda checked=False,identifier=c['id']:self.change_color(identifier),
                lambda value,identifier=c['id']:self.change_value(identifier,value),self.list)
            item.setSizeHint(QSize(240,max(36,row.sizeHint().height()+4)))
            self.list.setItemWidget(item,row);self.swatches[c['id']]=swatch;self.value_inputs[c['id']]=value_input
        index=next((i for i,c in enumerate(self.classes) if c['id']==current),0)
        self.list.setCurrentRow(index if self.classes else -1);self.list.blockSignals(False);self.select()

    def select(self,*args):
        row=self.list.currentRow();item=self.classes[row] if row>=0 else None
        self.name.setText(item['name'] if item else '');self.name.setCursorPosition(0);self.rename_button.setEnabled(item is not None)
        blocked=item is not None and item['id'] in self.used
        self.delete_button.setEnabled(item is not None and not blocked)
        self.message.setText(ui_text('dialogs.select.020') if blocked else '')

    def show_full_name(self,expanded):
        self.name_details.setVisible(expanded);self.expand_name_button.setText(ui_text('classes.collapse_name' if expanded else 'classes.expand_name'))

    def validate(self,items):
        try:validate_classes(items);return True
        except ValueError as error:self.message.setText(str(error));return False

    def add(self):
        if self.next_id>65534:self.message.setText(ui_text('dialogs.add.021'));return
        value=next_class_value(self.classes)
        if value>65534:self.message.setText(ui_text('classes.values_exhausted'));return
        from .class_colors import allocate_color
        item={'id':self.next_id,'name':self.name.text().strip(),'value':value,'color':allocate_color(self.next_id,self.classes)}
        if not self.validate(self.classes+[item]):return
        self.classes.append(item);self.next_id+=1;self.refresh(item['id'])

    def change_value(self,identifier,value):
        row=next(i for i,c in enumerate(self.classes) if c['id']==identifier)
        items=[dict(c) for c in self.classes];items[row]['value']=value
        if not self.validate(items):
            with QSignalBlocker(self.value_inputs[identifier]):self.value_inputs[identifier].setValue(class_value(self.classes[row]))
            return
        self.classes=items;self.message.clear()
        self.list.item(row).setData(Qt.ItemDataRole.AccessibleTextRole,ui_text('classes.row_accessible').format(items[row]['name'],value))

    def change_color(self,identifier):
        from .class_colors import class_color,normalize_color
        from .ui.color_controls import choose_color
        row=next(i for i,c in enumerate(self.classes) if c['id']==identifier)
        self.list.setCurrentRow(row);category=self.classes[row]
        color=choose_color(class_color(category),category['name'],self)
        if color is not None:
            category['color']=normalize_color(color);self.swatches[identifier].set_color(category['color'])

    def rename(self):
        row=self.list.currentRow()
        if row<0:return
        items=[dict(c) for c in self.classes];items[row]['name']=self.name.text().strip()
        if not self.validate(items):return
        self.classes=items;self.refresh(items[row]['id'])

    def remove(self):
        row=self.list.currentRow()
        if row>=0 and self.classes[row]['id'] not in self.used:self.classes.pop(row);self.refresh()

    def value(self):
        selected=self.list.currentItem()
        return self.classes,self.next_id,selected.data(Qt.ItemDataRole.UserRole) if selected else None

    def accept(self):
        for control in self.value_inputs.values():control.interpretText()
        row=self.list.currentRow()
        if row>=0 and self.name.text().strip()!=self.classes[row]['name']:
            self.rename()
            if self.name.text().strip()!=self.classes[row]['name']:return
        elif row<0 and self.name.text().strip():
            self.add()
            if not self.classes:return
        super().accept()


def dialog_buttons(parent):
    buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
    buttons.button(QDialogButtonBox.StandardButton.Ok).setText(ui_text('dialogs.dialog_buttons.001'))
    buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(ui_text('control_state.update_controls.012'))
    buttons.accepted.connect(parent.accept);buttons.rejected.connect(parent.reject)
    return buttons


class BandsDialog(QDialog):
    def __init__(self,image,parent=None):
        super().__init__(parent);self.setWindowTitle(ui_text('dialogs.__init__.006'));self.resize(450,270)
        layout=QVBoxLayout(self)
        if not image.get('suggested_bands'):layout.addWidget(QLabel(ui_text('dialogs.__init__.033')))
        form=QFormLayout();layout.addLayout(form);self.channels=[];self.ranges=[];self.range_widgets=[]
        recipe=image.get('display_recipe') or {};bands=recipe.get('bands') or image.get('suggested_bands') or [min(i,image['bands']) for i in [1,2,3]]
        for i,name in enumerate([ui_text('dialogs.__init__.022'),ui_text('dialogs.__init__.023'),ui_text('dialogs.__init__.024')]):
            row=QHBoxLayout();combo=QSpinBox();combo.setAlignment(Qt.AlignmentFlag.AlignCenter);combo.setRange(1,image['bands']);combo.setValue(bands[i]);row.addWidget(combo);self.channels.append(combo)
            limits_widget=QWidget();limits_layout=QHBoxLayout(limits_widget);limits_layout.setContentsMargins(0,0,0,0)
            lo=QDoubleSpinBox();hi=QDoubleSpinBox()
            for control in [lo,hi]:control.setAlignment(Qt.AlignmentFlag.AlignCenter);control.setRange(-1e12,1e12);control.setDecimals(4)
            limits_layout.addWidget(QLabel(ui_text('dialogs.__init__.034')));limits_layout.addWidget(lo);limits_layout.addWidget(QLabel('—'));limits_layout.addWidget(hi);row.addWidget(limits_widget);self.range_widgets.append(limits_widget);limits_widget.hide()
            limits=recipe.get('ranges',[[0,255]]*3)[i];lo.setValue(limits[0]);hi.setValue(limits[1]);self.ranges.append((lo,hi));form.addRow(name,row)
        self.stretch=QComboBox();self.stretch.addItems([ui_text('dialogs.__init__.025'),ui_text('dialogs.__init__.026')]);self.stretch.setToolTip(ui_text('dialogs.__init__.007'));form.addRow(ui_text('dialogs.__init__.008'),self.stretch)
        self.stretch.currentIndexChanged.connect(lambda index:[widget.setVisible(index==1) for widget in self.range_widgets])
        self.target=QComboBox();self.target.addItems([ui_text('dialogs.__init__.027'),ui_text('dialogs.__init__.028'),ui_text('dialogs.__init__.029')]);form.addRow(ui_text('dialogs.__init__.009'),self.target)
        layout.addWidget(dialog_buttons(self))

    def values(self):
        return [v.value() for v in self.channels],[[lo.value(),hi.value()] for lo,hi in self.ranges],self.stretch.currentIndex(),self.target.currentIndex()


class ModelDialog(QDialog):
    def __init__(self,config,parent=None):
        super().__init__(parent);self.setWindowTitle(ui_text('dialogs.__init__.010'));self.resize(600,260)
        layout=QVBoxLayout(self)
        form=QFormLayout();layout.addLayout(form);self.variant=QComboBox()
        self.variant.setItemDelegate(ModelItemDelegate(self.variant.view()))
        for spec in MODELS:
            path=config.get('checkpoint') if spec['variant']==config['variant'] and spec['backend']==config.get('backend','sam') else None
            state,location=weight_status(spec,path)
            self.variant.addItem(ui_text('dialogs.__init__.030').format(p0=spec['title'],p1=state,p2=memory_budget(spec)),spec['id'])
            family,_,size=spec['title'].partition(' · ')
            self.variant.setItemData(self.variant.count()-1,[family,size or '—',state,ui_text('dialogs.refresh_resource_info.017').format(p0=memory_budget(spec))],MODEL_COLUMNS_ROLE)
            self.variant.setItemData(self.variant.count()-1,str(location)+'\n'+memory_tooltip(spec),Qt.ItemDataRole.ToolTipRole)
        self.variant.setMaxVisibleItems(len(MODELS))
        selected=model_spec(config['variant'],config.get('backend','sam'))
        self.variant.setCurrentIndex(self.variant.findData(selected['id']));form.addRow(ui_text('dialogs.__init__.011'),self.variant)
        self.device=QComboBox();self.device.addItem(ui_text('dialogs.__init__.012'),'cuda');self.device.addItem('CPU','cpu');self.device.setCurrentIndex(self.device.findData(config['device']));form.addRow(ui_text('dialogs.__init__.013'),self.device)
        self.local=QPushButton(ui_text('dialogs.__init__.014'));self.local.setCheckable(True);layout.addWidget(self.local)
        self.weight_row=QWidget();row=QHBoxLayout(self.weight_row);row.setContentsMargins(0,0,0,0);self.path=QLineEdit(config['checkpoint']);row.addWidget(self.path);browse=QPushButton(ui_text('dialogs.__init__.015'));row.addWidget(browse);browse.clicked.connect(self.browse);layout.addWidget(self.weight_row);self.weight_row.hide();self.local.toggled.connect(self.weight_row.setVisible)
        if config['checkpoint']!=str(default_checkpoint(config['variant'],config.get('backend','sam'))):self.local.setChecked(True)
        self.variant.currentIndexChanged.connect(lambda:self.path.setText(str(default_checkpoint(self.selected_spec()['variant'],self.selected_spec()['backend']))))
        self.memory_info=QLabel();self.memory_info.setWordWrap(True);layout.addWidget(self.memory_info)
        self.weight_info=QLabel();self.weight_info.setProperty('role','muted');layout.addWidget(self.weight_info)
        self.path.textChanged.connect(self.refresh_resource_info);self.device.currentIndexChanged.connect(self.refresh_resource_info)
        self.variant.currentIndexChanged.connect(self.refresh_resource_info)
        self.refresh_resource_info()
        layout.addWidget(dialog_buttons(self))

    def refresh_resource_info(self):
        spec=self.selected_spec();state,path=weight_status(spec,self.path.text().strip() or None)
        self.memory_info.setText(memory_description(spec,self.device.currentData()=='cpu'));self.memory_info.setToolTip(memory_tooltip(spec))
        self.weight_info.setText(state+ui_text('dialogs.refresh_resource_info.031').format(p0=spec['bytes'] / 1024 ** 3));self.weight_info.setToolTip(str(path)+ui_text('dialogs.refresh_resource_info.032'))
        selected=self.variant.currentIndex();cpu=self.device.currentData()=='cpu'
        for i,item in enumerate(MODELS):
            item_state=state if i==selected else weight_status(item)[0]
            budget='CPU' if cpu else ui_text('dialogs.refresh_resource_info.017').format(p0=memory_budget(item))
            family,_,size=item['title'].partition(' · ')
            self.variant.setItemData(i,[family,size or '—',item_state,budget],MODEL_COLUMNS_ROLE)
            self.variant.setItemText(i,f"{item['title']}  ·  {item_state}  ·  {budget}")

    def browse(self):
        path,_=QFileDialog.getOpenFileName(self,ui_text('dialogs.browse.018'),'',ui_text('dialogs.browse.019'))
        if path:self.path.setText(path)

    def selected_spec(self):return next(s for s in MODELS if s['id']==self.variant.currentData())

    def value(self):
        spec=self.selected_spec()
        return {'backend':spec['backend'],'variant':spec['variant'],'device':self.device.currentData(),'execution':'auto','checkpoint':self.path.text().strip() or str(default_checkpoint(spec['variant'],spec['backend']))}


