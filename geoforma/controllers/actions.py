"""WorkbenchActions responsibilities in the Qt application layer."""
from __future__ import annotations
from ..ui.text import ui_text
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import QLabel, QDockWidget, QWidget, QVBoxLayout,QHBoxLayout,QSizePolicy,QToolBar,QToolButton,QWidgetAction,QMenu


class WorkbenchActions:
    def action(self,text,slot,shortcut=None,lock=True,*,widget=False):
        from ..operation_state import interaction_locked
        a=QWidgetAction(self) if widget else QAction(self);a.setText(text)
        a.triggered.connect(lambda checked=False:slot() if not interaction_locked(self) else None)
        if shortcut:a.setShortcut(QKeySequence(shortcut));a.setToolTip(text+'（'+shortcut+'）')
        if lock:self.actions_to_lock.append(a)
        return a

    def build_actions(self):
        from ..tool_icons import icon,visibility_icon
        from ..reference_images import MAIN_IMAGE_LABEL
        from ..ui.image_toolbar import ImageToolBar,ImageToolbarRow
        self.menuBar().hide()
        self.project_actions={'new':self.action(ui_text('actions.build_actions.010'),self.new),'open':self.action(ui_text('actions.build_actions.011'),self.open_dialog),
            'save':self.action(ui_text('actions.build_actions.012'),self.save,lock=False),'recover':self.action(ui_text('project.recover_previous'),self.recover_previous_work,lock=False)}
        for key,name in (('new','new_project'),('open','open_project'),('save','save'),('recover','recover_project')):self.project_actions[key].setIcon(icon(name))
        for a in self.project_actions.values():self.addAction(a)
        for key,action in self.project_actions.items():action.setProperty('feedback','primary' if key=='save' else 'dialog')
        self.import_action=self.action(ui_text('action.import_image'),self.import_dialog);self.addAction(self.import_action)
        self.raw_view_action=self.action(ui_text('actions.build_actions.001'),self.toggle_raw,lock=False,widget=True);self.raw_view_action.setCheckable(True)
        # Retain the existing action attribute; checked now means overlays visible.
        self.raw_view_action.setChecked(True)
        toolbar=ImageToolBar(ui_text('actions.build_actions.002'));toolbar.setMovable(False);toolbar.setIconSize(QSize(20,20));toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon);self.image_toolbar=toolbar
        toolbar.setObjectName('imageToolbar');toolbar.setIconSize(QSize(18,18))
        toolbar.setStyleSheet("QToolBar#imageToolbar{padding:4px 2px;spacing:1px;} QToolBar#imageToolbar QToolButton{padding:5px 2px;} QToolBar#imageToolbar::separator{width:1px;margin:5px 3px;}")
        self.mode_group=QActionGroup(self);self.mode_actions={}
        for text,mode in [(ui_text('actions.build_actions.015'),'positive'),(ui_text('actions.build_actions.016'),'negative'),(ui_text('actions.build_actions.017'),'box'),('绘制','draw_polygon'),(ui_text('reshape.title'),'reshape'),(ui_text('actions.build_actions.018'),'select_points'),(ui_text('actions.build_actions.019'),'select'),(ui_text('actions.build_actions.020'),'pan')]:
            a=self.action(text,lambda checked=False,m=mode:self.begin_reshape(auto=True) if m=='reshape' else self.set_tool(m),lock=False);a.setIcon(icon(mode));a.setCheckable(True);self.mode_group.addAction(a);toolbar.addAction(a);self.mode_actions[mode]=a
            if mode in ('positive','negative','box','select_points','select'):
                a.setToolTip(a.toolTip()+'\n切换此工具会清除未完成的重塑线，保留已有标签。')
            elif mode=='pan':a.setToolTip(a.toolTip()+'\n平移时保留重塑线，切回重塑可继续绘制。')
            if mode=='reshape':
                a.setToolTip(ui_text('reshape.title')+'\n'+ui_text('reshape.tooltip'));self.reshape_button=toolbar.widgetForAction(a)
        self.mode_actions['pan'].setChecked(True);toolbar.addSeparator()
        fit=self.action(ui_text('actions.build_actions.003'),self.view.fit_image,lock=False);fit.setIcon(icon('fit'));toolbar.addAction(fit);self.fit_action=fit
        native=self.action('1:1',self.zoom_native,lock=False);native.setIcon(icon('native'));toolbar.addAction(native);toolbar.addSeparator();self.native_zoom_action=native
        self.undo_prompt_action=self.action(ui_text('actions.build_actions.004'),self.undo_context,'Ctrl+Z');toolbar.addAction(self.undo_prompt_action)
        self.redo_prompt_action=self.action(ui_text('actions.build_actions.005'),self.redo_context,'Ctrl+Shift+Z');toolbar.addAction(self.redo_prompt_action)
        self.undo_prompt_action.setIcon(icon('undo'));self.redo_prompt_action.setIcon(icon('redo'))
        for action in (fit,native,self.undo_prompt_action,self.redo_prompt_action):action.setProperty('feedback','navigation')
        self.undo_label_action=self.action(ui_text('actions.build_actions.006'),self.undo_label,'Ctrl+Alt+Z');self.addAction(self.undo_label_action)
        self.delete_action=self.action(ui_text('action.delete'),self.delete_selection,'Del');self.delete_action.setIcon(icon('delete'));toolbar.addAction(self.delete_action)
        self.delete_action.setProperty('feedback','danger')
        for a in [self.undo_prompt_action,self.redo_prompt_action,self.delete_action]:
            a.setProperty('iconOnly',True)
            toolbar.widgetForAction(a).setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        spacer=QWidget();spacer.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Preferred);toolbar.addWidget(spacer)
        self.source_controls=QWidget();self.source_controls.setFixedHeight(46)
        source_row=QHBoxLayout(self.source_controls);source_row.setContentsMargins(3,0,3,0);source_row.setSpacing(3)
        self.visibility_toolbar=QToolBar();self.visibility_toolbar.setMovable(False);self.visibility_toolbar.setIconSize(QSize(18,18))
        self.visibility_toolbar.setStyleSheet('QToolBar{border:0;padding:0;spacing:0;} QToolButton{padding:4px;}')
        from ..ui.visibility_button import VisibilityButton
        self.raw_view_action.setIcon(visibility_icon());self.raw_view_action.setProperty('iconOnly',True)
        self.raw_view_action.setDefaultWidget(VisibilityButton(self.raw_view_action));self.visibility_toolbar.addAction(self.raw_view_action)
        self.visibility_toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly);source_row.addWidget(self.visibility_toolbar)
        self.main_image_button=QToolButton();self.main_image_button.setFixedSize(96,30);self.main_image_button.setText(MAIN_IMAGE_LABEL);self.main_image_button.setCheckable(True)
        self.main_image_button.setToolTip('用于模型分割与标签定位的主影像');self.main_image_button.clicked.connect(lambda:self.switch_reference(None));source_row.addWidget(self.main_image_button)
        from ..ui.reference_switcher import ReferenceSwitcher
        self.reference_switch_holder=ReferenceSwitcher();self.reference_switches=self.reference_switch_holder.buttons_widget
        self.reference_switch_holder.selected.connect(self.switch_reference)
        self.source_controls.setStyleSheet('QToolButton{padding:4px 8px;border:1px solid #d5e3e7;border-radius:4px;background:white;color:#30525c;} QToolButton:checked{background:#def3ef;border-color:#92d4cd;color:#087f88;}')
        source_row.addWidget(self.reference_switch_holder)
        self.settings_button=QToolButton();self.settings_button.setFixedSize(30,30);self.settings_button.setIcon(icon('settings'))
        self.settings_button.setIconSize(QSize(18,18));self.settings_button.setAutoRaise(True)
        self.settings_button.setStyleSheet('QToolButton{padding:0;background:transparent;border:1px solid transparent;border-radius:4px;} QToolButton:focus{border-color:transparent;} QToolButton:hover{background:#edf5f6;border-color:#d2e6e7;} QToolButton::menu-indicator{image:none;width:0;}')
        self.settings_button.setToolTip('设置');self.settings_button.setAccessibleName('设置');self.settings_button.setProperty('feedback','normal')
        self.settings_menu=QMenu(self.settings_button);self.settings_menu.setMinimumWidth(160)
        self.reference_manage_action=self.action('参考管理',self.manage_references,lock=False)
        self.resources_action=self.action('资源配置',self.configure_resources,lock=False);self.settings_menu.addAction(self.resources_action)
        self.settings_menu.addSeparator()
        self.data_directory_action=self.action('数据目录',self.open_data_directory,lock=False);self.settings_menu.addAction(self.data_directory_action)
        self.documentation_action=self.action(ui_text('actions.help.008'),self.help,lock=False)
        self.dependencies_action=self.action('依赖库版本',self.show_dependency_versions,lock=False)
        self.task_log_action=self.action(ui_text('imagery.left.010'),lambda:self.log_dock.setVisible(not self.log_dock.isVisible()),lock=False)
        self.settings_button.setMenu(self.settings_menu);self.settings_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        source_row.addWidget(self.settings_button)
        # Keep image operations above the image instead of spanning both sidebars.
        central=QWidget();central.setMinimumWidth(400);layout=QVBoxLayout(central);layout.setContentsMargins(0,0,0,0);layout.setSpacing(0)
        top=ImageToolbarRow(toolbar,self.source_controls,self.resize_reference_strip)
        layout.addWidget(top);layout.addWidget(self.view,1);self.setCentralWidget(central)


    def dock(self,title,widget,area):
        dock=QDockWidget(title,self);dock.setObjectName(title);dock.setWidget(widget);dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        heading=QLabel(title);heading.setProperty('role','panelTitle');heading.setFixedHeight(27);dock.setTitleBarWidget(heading)
        self.addDockWidget(area,dock);return dock

    def build_left(self):
        from ..ui.panels.imagery import left
        left(self)

    def build_right(self):
        from ..ui.panels.annotation import right
        right(self)

    def build_bottom(self):
        from ..ui.panels.status import bottom
        bottom(self)

    def help(self):
        from ..ui.information import DocumentationDialog
        from ..ui.modal import dialog_result
        dialog_result(DocumentationDialog(self))

    def show_dependency_versions(self):
        from ..ui.information import DependencyVersionsDialog
        from ..ui.modal import dialog_result
        dialog_result(DependencyVersionsDialog(self))

