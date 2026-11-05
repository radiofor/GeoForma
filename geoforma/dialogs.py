from .ui.text import ui_text
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QFormLayout,QLabel,
    QSpinBox,QDoubleSpinBox,QHBoxLayout,QLineEdit,QPushButton,QFileDialog,QWidget)
from .weights import default_checkpoint
from PySide6.QtCore import Qt
from .model_catalog import MODELS,model_spec
from .model_status import weight_status,memory_budget,memory_description,memory_tooltip
from .ui.reference_name import ReferenceNameDialog
from .ui.centered_combo import CenteredComboBox as QComboBox
from .ui.model_combo import ModelItemDelegate,MODEL_COLUMNS_ROLE


from .ui.classes_dialog import ClassesDialog
from .ui.modal import dialog_buttons


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


