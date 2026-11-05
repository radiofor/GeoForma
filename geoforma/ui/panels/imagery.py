"""品牌和项目固定在左栏顶部，模型与影像在下方按需滚动。"""
from ...ui.text import ui_text
from ...window_preferences import LEFT_SIDEBAR_WIDTHS
from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget, QToolButton
from ...tool_icons import icon
from ...theme import BrandHeader, PanelGroupBox as QGroupBox
from ..controls import action_button, scroll_panel, ElidedLabel,DeviceStatusLabel,TrailingIconButton,CenteredIconActionButton
from ..raster_list import RasterItemDelegate, RasterListSizer
from ..readouts import RasterInfo
from ..loading_button import LoadingButton
from ..layouts import card_layout,polish_controls,reserve_scrollbar


def left(w):
    sidebar = QWidget()
    sidebar.setProperty('role', 'sidePanel')
    sidebar.setMinimumWidth(LEFT_SIDEBAR_WIDTHS[0])
    sidebar.setMaximumWidth(LEFT_SIDEBAR_WIDTHS[1])
    column = QVBoxLayout(sidebar)
    column.setContentsMargins(8, 8, 8, 6)
    column.setSpacing(10)
    w.brand_header = BrandHeader()
    column.addWidget(w.brand_header)
    column.addWidget(build_project(w))

    widget = QWidget()
    widget.setProperty('role', 'sidePanel')
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 2)
    layout.setSpacing(10)
    layout.addWidget(build_model(w))
    layout.addWidget(build_imagery(w),1)
    layout.addWidget(build_tools(w))
    w.image_scroll = scroll_panel(widget, 0, LEFT_SIDEBAR_WIDTHS[1])
    w.image_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    column.addWidget(w.image_scroll, 1)
    polish_controls(sidebar)
    w.raster_list_sizer = RasterListSizer(w.images, w.image_scroll)
    w.image_dock = w.dock(ui_text('imagery.left.007'), sidebar, Qt.DockWidgetArea.LeftDockWidgetArea)
    # “影像”是数据分区标题，品牌不再位于整个左栏的“影像”标题之下。
    title_bar = QWidget()
    title_bar.setFixedHeight(0)
    w.image_dock.setTitleBarWidget(title_bar)
    w.resizeDocks([w.image_dock], [288], Qt.Orientation.Horizontal)


def build_project(w):
    project = QGroupBox(ui_text('imagery.left.002'))
    layout = card_layout(project)
    layout.setSpacing(6)
    w.project_title = ElidedLabel(ui_text('projects.new.001'))
    w.project_title.setProperty('role', 'project')
    w.project_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    w.project_title.setFixedHeight(32)
    title_row=QHBoxLayout();title_row.setContentsMargins(0,0,0,0);title_row.setSpacing(4)
    title_row.addWidget(w.project_title,1)
    w.project_directory_button=QToolButton();w.project_directory_button.setIcon(icon('open_project'))
    w.project_directory_button.setIconSize(QSize(16,16));w.project_directory_button.setFixedSize(32,32)
    w.project_directory_button.setToolTip('打开项目所在文件夹');w.project_directory_button.setAccessibleName('打开项目所在文件夹')
    w.project_directory_button.setEnabled(bool(w.project_path))
    w.project_directory_button.clicked.connect(w.open_project_directory)
    title_row.addWidget(w.project_directory_button);layout.addLayout(title_row)
    for keys in [('new', 'open'), ('save', 'recover')]:
        row = QHBoxLayout()
        row.setSpacing(6)
        for key in keys:
            button=CenteredIconActionButton(w.project_actions[key])
            if key=='recover':w.recover_button=button
            row.addWidget(button, 1)
        layout.addLayout(row)
    project.setFixedHeight(150)
    return project


def build_model(w):
    model = QGroupBox(ui_text('imagery.left.001'))
    layout = card_layout(model)
    layout.setContentsMargins(10, 30, 10, 12)
    w.model_button = TrailingIconButton()
    w.model_button.setProperty('role','modelSelector')
    w.model_button.setProperty('feedback','dialog')
    w.model_button.setIcon(icon('search'))
    w.model_button.setIconSize(QSize(14, 14))
    w.model_button.clicked.connect(w.configure_model)
    w.model_runtime = DeviceStatusLabel(text_padding=4)
    w.model_runtime.setAlignment(Qt.AlignmentFlag.AlignCenter)
    w.model_runtime.setProperty('role', 'deviceStatus')
    w.model_runtime.setFixedHeight(32)
    w.model_runtime.setMinimumWidth(114)
    w.model_runtime.setMaximumWidth(220)
    w.model_button.setFixedHeight(32)
    model.setFixedHeight(74)
    status_row = QHBoxLayout()
    status_row.setSpacing(4)
    status_row.addWidget(w.model_button, 56)
    status_row.addWidget(w.model_runtime, 44)
    layout.addLayout(status_row)
    return model


def build_imagery(w):
    imagery = QGroupBox(ui_text('imagery.left.007'))
    layout = card_layout(imagery)
    layout.setSpacing(6)
    w.import_button = LoadingButton(ui_text('action.import_image'))
    w.import_button.setProperty('role', 'import')
    w.import_button.clicked.connect(w.import_dialog)
    layout.addWidget(w.import_button)
    references=QHBoxLayout();references.setSpacing(6)
    w.import_reference_button=LoadingButton('导入参考');w.import_reference_button.setProperty('role','import');w.import_reference_button.clicked.connect(w.import_references_dialog)
    w.reference_manage_button=action_button(w.reference_manage_action)
    references.addWidget(w.import_reference_button,1);references.addWidget(w.reference_manage_button,1);layout.addLayout(references)
    w.images = QListWidget()
    w.images.setMouseTracking(True)
    reserve_scrollbar(w.images)
    delegate=RasterItemDelegate(w.images);delegate.reviewToggled.connect(w.toggle_image_review);w.images.setItemDelegate(delegate)
    from ..raster_presenter import RasterListPresenter
    w.raster_presenter=RasterListPresenter(w.images)
    w.images.setMinimumHeight(RasterListSizer.minimum_height)
    w.images.setSpacing(3)
    w.images.currentRowChanged.connect(w.change_image)
    layout.addWidget(w.images,1)
    w.image_info = RasterInfo()
    layout.addWidget(w.image_info)
    row = QHBoxLayout()
    row.setSpacing(6)
    w.bands_button = QPushButton(ui_text('imagery.left.003'))
    w.bands_button.setProperty('feedback','dialog')
    w.bands_button.clicked.connect(w.configure_bands)
    row.addWidget(w.bands_button)
    w.crs_button = QPushButton(ui_text('imagery.left.004'))
    w.crs_button.setProperty('feedback','dialog')
    w.crs_button.clicked.connect(w.assign_crs)
    row.addWidget(w.crs_button)
    layout.addLayout(row)
    w.reprepare_button = QPushButton(ui_text('imagery.left.005'))
    w.reprepare_button.clicked.connect(w.preprocess)
    layout.addWidget(w.reprepare_button)
    return imagery


def build_tools(w):
    tools = QGroupBox(ui_text('group.help_diagnostics'))
    w.help_group=tools
    layout = card_layout(tools)
    layout.setSpacing(5)
    row = QHBoxLayout()
    row.setSpacing(6)
    for action in (w.documentation_action,w.task_log_action,w.dependencies_action):row.addWidget(action_button(action),1)
    layout.addLayout(row)
    return tools
