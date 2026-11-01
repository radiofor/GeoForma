"""One centered status row, with a persistent progress/result area."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel,QPushButton,QPlainTextEdit,QWidget,QHBoxLayout,QFrame,QToolButton,QMenu,QStackedWidget
from ..text import ui_text
from ..controls import ElidedLabel
from ..status_visuals import StatusBadge,StatusDetail
from ..status_bar import WorkbenchStatusBar
from ..background_activity import BackgroundActivity
from ..task_progress import TaskProgressPresentation
from ..progress_bar import TaskProgressBar
from ..layouts import reserve_space


def bottom(w):
    center=Qt.AlignmentFlag.AlignVCenter
    w.task_text=StatusDetail();w.task_text.setFixedHeight(26);w.task_text.setAlignment(Qt.AlignmentFlag.AlignLeft|center)
    bar=WorkbenchStatusBar(w.task_text,w);w.setStatusBar(bar);bar.setFixedHeight(42);bar.setSizeGripEnabled(False)
    bar.setStyleSheet('QStatusBar{background:#f7fafb;border-top:1px solid #dce7eb;padding:0;} QStatusBar::item{border:0;} QStatusBar QLabel{padding:0;margin:0;}')
    w.task_text.setStyleSheet('color:#496672;');bar.notice.setStyleSheet('color:#147b7e;padding:0;')
    bar.notice.setAlignment(Qt.AlignmentFlag.AlignLeft|center);bar.notice.setFixedHeight(26)
    w.state_label=StatusBadge(ui_text('control_state.update_controls.025'));w.state_label.setProperty('role','status')
    w.state_label.setFixedSize(96,26);w.state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    w.state_label.setStyleSheet('padding:0;background:transparent;border:0;')
    w.edit_status=StatusDetail(ui_text('prompts.update_draft_info.011'))
    for label in (w.edit_status,):
        label.setAlignment(Qt.AlignmentFlag.AlignCenter);label.setFixedHeight(26);label.setStyleSheet('color:#758b95;padding:0;')
    w.context_status=w.edit_status;w.context_status.setFixedSize(170,26)
    w.background_button=QToolButton();w.background_button.setFixedSize(86,26);w.background_button.setEnabled(False)
    reserve_space(w.background_button);w.background_button.hide()
    w.background_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    w.background_button.setStyleSheet('QToolButton{border:1px solid transparent;border-radius:5px;padding:0 8px 0 0;color:#6b8490;background:transparent;} QToolButton:enabled{color:#397887;background:#edf5f7;border-color:#dcebee;} QToolButton:hover{background:#e2f0f3;} QToolButton::menu-indicator{width:8px;subcontrol-position:right center;right:5px;}')
    menu=QMenu(w.background_button);w.background_button.setMenu(menu)
    w.background_activity=BackgroundActivity(w,w.background_button,menu)
    w.progress=TaskProgressBar()
    w.import_button.bind_progress(w.progress.model,'import')
    w.import_reference_button.bind_progress(w.progress.model,'reference_import')
    w.progress_count=ElidedLabel('');w.progress_count.setAlignment(Qt.AlignmentFlag.AlignRight|center)
    w.progress_count.setFixedSize(105,26);w.progress_count.setStyleSheet('color:#456976;font-weight:600;padding:0;')
    w.cancel_button=QPushButton(ui_text('control_state.update_controls.011'));w.cancel_button.setFixedSize(64,26)
    w.cancel_button.setProperty('feedback','cancel')
    w.cancel_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    w.cancel_button.setEnabled(False);w.cancel_button.clicked.connect(w.cancel)
    w.cancel_button.setStyleSheet('QPushButton{padding:0;border:1px solid #d6e4e8;border-radius:5px;background:transparent;color:#64808d;} QPushButton:hover{background:#fff1ed;border-color:#e7beb4;color:#a85a44;} QPushButton:pressed{background:#f9e1d9;}')
    w.progress_result=StatusBadge(result=True);w.progress_result.setFixedSize(72,26);w.progress_result.setAlignment(Qt.AlignmentFlag.AlignCenter)
    w.progress_action=QStackedWidget();w.progress_action.setFixedSize(72,26)
    w.cancel_button.setFixedWidth(72)
    w.progress_action.addWidget(w.cancel_button);w.progress_action.addWidget(w.progress_result);w.progress_action.setCurrentIndex(1)
    w.progress_panel=QFrame();w.progress_panel.setObjectName('taskProgressGroup');w.progress_panel.setFixedHeight(34)
    w.progress_panel.setStyleSheet('QFrame#taskProgressGroup{background:#eef5f6;border:1px solid #dce8eb;border-radius:7px;}')
    progress_row=QHBoxLayout(w.progress_panel);progress_row.setContentsMargins(8,0,8,0);progress_row.setSpacing(10)
    for control in (w.state_label,w.progress_count,w.progress,w.progress_action):progress_row.addWidget(control,0,center)
    for control in (w.progress_count,w.progress,w.progress_action):control.hide()
    w.progress_presentation=TaskProgressPresentation(w)
    content=QWidget();row=QHBoxLayout(content);row.setContentsMargins(14,0,14,0);row.setSpacing(12)
    row.addWidget(w.progress_panel,0,center);row.addWidget(bar.text_slot,1,center)
    row.addWidget(w.background_button,0,center)
    row.addWidget(w.context_status,0,center)
    bar.set_content(content)
    w.cursor_label=QLabel(w);w.cursor_label.hide()
    w.log=QPlainTextEdit();w.log.setReadOnly(True);w.log.setMaximumBlockCount(600)
    w.log_dock=w.dock(ui_text('imagery.left.010'),w.log,Qt.DockWidgetArea.BottomDockWidgetArea);w.log_dock.setMaximumHeight(150);w.log_dock.hide()
