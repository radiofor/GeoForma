"""Compact desktop panels; application operations are supplied by MainWindow."""
from ...ui.text import ui_text
from ...domain import DEFAULT_FILL_HOLES
from ...window_preferences import RIGHT_SIDEBAR_WIDTHS
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton, QAbstractItemView, QCheckBox, QLineEdit, QStackedWidget,QDoubleSpinBox
from ...theme import PanelGroupBox as QGroupBox
from ..controls import scroll_panel
from ..readouts import PromptCounters
from ..centered_combo import CenteredComboBox
from ..layouts import card_layout,polish_controls,reserve_scrollbar

def right(w):
    widget=QWidget();widget.setProperty('role','sidePanel')
    layout=QVBoxLayout(widget);layout.setContentsMargins(8,8,8,8);layout.setSpacing(8)
    w.preprocess_button=w.reprepare_button
    build_smoothing(w)
    w.mode_settings=QStackedWidget();layout.addWidget(w.mode_settings)
    build_prompt_tools(w,w.mode_settings)
    w.mode_settings.setCurrentWidget(w.prompt_group)
    build_editor(w,layout)
    build_label_list(w,layout)
    from PySide6.QtGui import QShortcut,QKeySequence
    for name,target in (('save_label_shortcut',w.view),('table_save_shortcut',w.labels_table)):
        shortcut=QShortcut(target);shortcut.setKeys([QKeySequence('Return'),QKeySequence('Enter')])
        shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut);shortcut.setAutoRepeat(False)
        shortcut.activated.connect(w.save_label_with_enter);setattr(w,name,shortcut)
    w.reshape_alternate_shortcut=QShortcut(QKeySequence('R'),w.view)
    w.reshape_alternate_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
    w.reshape_alternate_shortcut.setAutoRepeat(False);w.reshape_alternate_shortcut.activated.connect(w.reshape_alternate)
    w.reshape_cancel_shortcut=QShortcut(QKeySequence('Escape'),w)
    w.reshape_cancel_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
    w.reshape_cancel_shortcut.setAutoRepeat(False);w.reshape_cancel_shortcut.setEnabled(False)
    w.reshape_cancel_shortcut.activated.connect(w.cancel_reshape)
    build_export(w,layout)
    polish_controls(widget)
    w.mode_settings.setFixedHeight(w.prompt_group.layout().minimumSize().height()+2)
    w.editor_scroll=scroll_panel(widget,*RIGHT_SIDEBAR_WIDTHS)
    reserve_scrollbar(w.editor_scroll)
    w.annotation_dock=w.dock(ui_text('annotation.right.003'),w.editor_scroll,Qt.DockWidgetArea.RightDockWidgetArea)


def build_smoothing(w):
    w.smoothing_controls=QWidget();w.smoothing_controls.setFixedHeight(32)
    row=QHBoxLayout(w.smoothing_controls);row.setContentsMargins(0,0,0,0);row.setSpacing(6)
    from ...smoothing import settings
    w.smooth_enabled=QCheckBox('平滑');w.smooth_enabled.setChecked(settings(w.project,'individual')['enabled']);row.addWidget(w.smooth_enabled)
    row.addStretch()
    field=QWidget();field.setFixedWidth(112);value_row=QHBoxLayout(field);value_row.setContentsMargins(0,0,0,0);value_row.setSpacing(4)
    w.smooth_value=QDoubleSpinBox();w.smooth_value.setAlignment(Qt.AlignmentFlag.AlignCenter);w.smooth_value.setDecimals(0);w.smooth_value.setRange(1,5);w.smooth_value.setSingleStep(1);w.smooth_value.setValue(1);value_row.addWidget(w.smooth_value,1)
    w.smooth_unit=QLabel('像素');w.smooth_unit.setFixedWidth(w.smooth_unit.fontMetrics().horizontalAdvance('像素')+2);w.smooth_unit.setAlignment(Qt.AlignmentFlag.AlignCenter)
    value_row.addWidget(w.smooth_unit);row.addWidget(field)
    for control in (w.smooth_enabled,w.smooth_value):control.setToolTip('对当前模式全部标签应用平滑，保存与导出使用当前设置。单位：原始影像像素；默认值：1。关闭后显示原始轮廓。')
    w.smooth_enabled.toggled.connect(w.smoothing_changed);w.smooth_value.valueChanged.connect(w.smoothing_changed)


def add_smoothing_slot(w,group,layout):
    slot=QWidget();slot.setFixedHeight(32)
    row=QVBoxLayout(slot);row.setContentsMargins(0,0,0,0);row.setSpacing(0)
    group.smoothing_slot=slot;layout.addWidget(slot)
    if w.smoothing_controls.parentWidget() is None:row.addWidget(w.smoothing_controls)


def build_prompt_tools(w,stack):
    w.prompt_group=QGroupBox(ui_text('layout.prompt_tools'));body=card_layout(w.prompt_group)
    w.prompt_counters=PromptCounters();body.addWidget(w.prompt_counters)
    options=QHBoxLayout();options.setContentsMargins(0,0,0,0)
    w.single_polygon=QCheckBox(ui_text('option.single_polygon'));w.single_polygon.setChecked(w.project.get('workspace',{}).get('single_polygon',False));w.single_polygon.setToolTip(ui_text('option.single_polygon_hint'));w.single_polygon.toggled.connect(w.single_polygon_changed);options.addWidget(w.single_polygon)
    options.addStretch()
    w.fill_holes=QCheckBox('填充洞');w.fill_holes.setChecked(w.project.get('workspace',{}).get('fill_holes',DEFAULT_FILL_HOLES));w.fill_holes.toggled.connect(w.fill_holes_changed);options.addWidget(w.fill_holes,0,Qt.AlignmentFlag.AlignRight);body.addLayout(options)
    add_smoothing_slot(w,w.prompt_group,body)
    row=QHBoxLayout();row.setSpacing(6)
    w.apply_button=QPushButton(ui_text('action.apply'));w.apply_button.setObjectName('primary');w.apply_button.setToolTip(ui_text('annotation.build_editor.013'));w.apply_button.clicked.connect(w.predict);row.addWidget(w.apply_button,1)
    w.auto_apply=QCheckBox(ui_text('option.auto_apply'));w.auto_apply.setChecked(True);w.auto_apply.setToolTip(ui_text('annotation.build_editor.015'));w.auto_apply.toggled.connect(w.auto_apply_changed);row.addWidget(w.auto_apply)
    w.clear_points_button=QPushButton(ui_text('action.clear_points'));w.clear_points_button.setToolTip(ui_text('action.clear_points_hint'));w.clear_points_button.clicked.connect(w.clear_points);row.addWidget(w.clear_points_button,1);body.addLayout(row)
    w.delete_points_button=QPushButton(w);w.delete_points_button.clicked.connect(w.delete_points);w.delete_points_button.hide()
    stack.addWidget(w.prompt_group)




def build_editor(w,layout):
    w.editor_group=QGroupBox(ui_text('prompts.update_draft_info.012'));editor=card_layout(w.editor_group)
    row=QHBoxLayout();row.setSpacing(6);row.addWidget(QLabel(ui_text('annotation.build_editor.047')))
    w.classes=CenteredComboBox();w.classes.expand_popup=True;w.classes.setPlaceholderText(ui_text('annotation.build_editor.009'));w.classes.currentIndexChanged.connect(w.class_changed);row.addWidget(w.classes,1)
    w.classes_button=QPushButton(ui_text('annotation.build_editor.010'));w.classes_button.setFixedWidth(48);w.classes_button.clicked.connect(w.manage_classes);row.addWidget(w.classes_button);editor.addLayout(row)
    w.classes_button.setProperty('feedback','dialog')
    row=QHBoxLayout();row.setSpacing(6)
    w.new_target_button=QPushButton(ui_text('action.cancel_edit'));w.new_target_button.setShortcut('Esc');w.new_target_button.setToolTip(ui_text('annotation.build_editor.018'));w.new_target_button.clicked.connect(w.clear_draft);row.addWidget(w.new_target_button,1)
    w.confirm_button=QPushButton(ui_text('action.confirm'));w.confirm_button.setObjectName('primary');w.confirm_button.setToolTip(ui_text('annotation.build_editor.016'));w.confirm_button.clicked.connect(w.confirm);row.addWidget(w.confirm_button,1);editor.addLayout(row)
    w.editor_group.setFixedHeight(116);layout.addWidget(w.editor_group)


def build_label_list(w,layout):
    from ..label_table import LabelTable
    w.labels_table=LabelTable()
    w.labels_table.setHorizontalHeaderLabels(['序号',ui_text('annotation.build_label_list.050'),ui_text('annotation.build_label_list.051')])
    w.labels_table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
    w.labels_table.setMinimumHeight(120)
    w.labels_table.verticalHeader().hide();w.labels_table.setShowGrid(False);w.labels_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);w.labels_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection);w.labels_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    w.labels_table.itemSelectionChanged.connect(w.table_selected);w.labels_table.cellDoubleClicked.connect(lambda *_:w.zoom_selected());layout.addWidget(w.labels_table,1)
    from ..label_table import LabelTablePresenter
    w.label_presenter=LabelTablePresenter(w.labels_table)
    from ..category_buttons import CategoryButtons
    w.category_buttons=CategoryButtons();w.category_buttons.requested.connect(w.change_selected_label_class);w.category_buttons.nameHovered.connect(w.show_category_name)
    layout.addWidget(w.category_buttons)


def build_export(w,layout):
    export_group=QGroupBox(ui_text('annotation.build_export.028'));w.export_group=export_group;export_layout=card_layout(export_group)
    form=QFormLayout();form.setHorizontalSpacing(6);form.setVerticalSpacing(6)
    from ...export_settings import VECTOR_FORMATS
    w.export_kind=CenteredComboBox();w.export_kind.setMinimumWidth(0);w.export_kind.setAccessibleName('导出格式')
    for name,suffix,_ in VECTOR_FORMATS:w.export_kind.addItem(name,suffix)
    form.addRow('导出格式',w.export_kind)
    w.export_crs_input=QLineEdit();w.export_crs_input.setAlignment(Qt.AlignmentFlag.AlignCenter);w.export_crs_input.setMinimumWidth(0);w.export_crs_input.editingFinished.connect(w.commit_export_crs)
    w.export_crs_input.setAccessibleName('标签投影');w.export_crs_input.setPlaceholderText('—');form.addRow('标签投影',w.export_crs_input)
    w.export_crs_input.setToolTip(ui_text('annotation.build_export.032'))
    w.export_label_field_input=QLineEdit();w.export_label_field_input.setAlignment(Qt.AlignmentFlag.AlignCenter);w.export_label_field_input.setMinimumWidth(0)
    w.export_label_field_input.setAccessibleName('标签字段名');w.export_label_field_input.setPlaceholderText('class_value')
    w.export_label_field_input.setToolTip('导出属性表中存放标签值的字段名，默认 class_value。支持字母、汉字、数字和下划线；SHP 最多 10 个 UTF-8 字节。')
    w.export_label_field_input.editingFinished.connect(w.commit_export_label_field);form.addRow('标签字段名',w.export_label_field_input);export_layout.addLayout(form)
    w.export_kind.currentIndexChanged.connect(lambda _index:w.export_format_changed())
    w.vector_export_button=QPushButton('导出标签');w.vector_export_button.clicked.connect(lambda:w.export())
    export_layout.addWidget(w.vector_export_button);layout.addWidget(export_group)
    export_group.setFixedHeight(188)

