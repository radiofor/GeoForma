"""Nonblocking, animated feedback during a safe desktop shutdown."""
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel
from ..branding import application_icon
from .text import ui_text
from .progress_bar import TaskProgressBar,COMPLETION_HOLD_MS


class ShutdownDialog(QDialog):
    def __init__(self,parent,phase,step=None):
        super().__init__(parent,Qt.WindowType.Dialog|Qt.WindowType.CustomizeWindowHint|Qt.WindowType.WindowTitleHint)
        self.setWindowTitle('GeoForma');self.setWindowModality(Qt.WindowModality.WindowModal);self.setFixedWidth(390)
        layout=QVBoxLayout(self);layout.setContentsMargins(24,22,24,22);layout.setSpacing(14)
        row=QHBoxLayout();logo=QLabel();logo.setPixmap(application_icon().pixmap(44,44));row.addWidget(logo)
        title=QLabel(ui_text('shutdown.title'));title.setStyleSheet('font-size:17px;font-weight:600;color:#172f3d;');row.addWidget(title,1);layout.addLayout(row)
        self.phase_label=QLabel();self.phase_label.setWordWrap(True);layout.addWidget(self.phase_label)
        self.progress=TaskProgressBar(expanding=True,smooth=True);self.progress.model.begin('退出清理','shutdown');layout.addWidget(self.progress)
        self.finishing=False;self.on_finished=None
        self.completion_timer=QTimer(self);self.completion_timer.setSingleShot(True);self.completion_timer.setInterval(COMPLETION_HOLD_MS)
        self.completion_timer.timeout.connect(self._dismiss);self.progress.completionPainted.connect(self._completed_frame)
        hint=QLabel(ui_text('shutdown.hint'));hint.setProperty('role','muted');layout.addWidget(hint)
        def refresh():
            text=phase();self.phase_label.setText(text)
            current=step() if step else 0
            self.progress.model.report(max(self.progress.model.state.current,current),3,text)
        self.timer=QTimer(self);self.timer.setInterval(200);self.timer.timeout.connect(refresh)
        refresh();self.timer.start()

    def reject(self):pass  # Escape must not hide ongoing cleanup.

    def closeEvent(self,event):event.ignore()

    def finish(self,outcome='complete',on_finished=None):
        self.timer.stop()
        if outcome!='complete':
            self.completion_timer.stop();self.on_finished=None;self.finishing=False;self.progress.model.finish(outcome);self.hide();return
        if self.finishing:return
        self.finishing=True;self.on_finished=on_finished;self.phase_label.setText('清理完成')
        self.progress.model.finish('complete','清理完成')

    def _completed_frame(self):
        if self.finishing:self.completion_timer.start()

    def _dismiss(self):
        self.hide();callback=self.on_finished;self.on_finished=None
        if callback:callback()
