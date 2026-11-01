"""Optional data choices made before uninstalling GeoForma."""
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import QCheckBox, QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout


class UninstallCleanupDialog(QDialog):
    """Collect choices only; accepting or rejecting does not delete files."""

    def __init__(self, resource_path='', parent=None, *, allow_cleanup=True, unavailable_reason=''):
        super().__init__(parent)
        self.setWindowTitle('卸载 GeoForma')
        self.resize(700, 460)
        self.setMinimumWidth(620)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)

        title = QLabel('选择要清理的数据')
        title.setProperty('role', 'dialogTitle')
        layout.addWidget(title)
        note = QLabel('卸载程序会移除 GeoForma。以下数据默认保留，请按需勾选要删除的内容。')
        note.setWordWrap(True)
        layout.addWidget(note)
        if resource_path:
            location = QLabel('当前资源目录：' + str(resource_path))
            location.setWordWrap(True)
            location.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
            layout.addWidget(location)
        if not allow_cleanup:
            warning = QLabel(unavailable_reason or '无法确认当前用户的数据归属，数据清理不可用，卸载时将保留数据。')
            warning.setWordWrap(True)
            layout.addWidget(warning)

        self.choices = {}
        rows = (
            ('caches', '删除影像缓存和日志', '影像缓存可重新生成；日志删除后无法查看。'),
            ('models', '删除模型权重和 PyTorch 运行库', '下次使用相关功能时需要重新下载或导入。'),
            ('settings', '删除软件设置', '清除界面和使用偏好；为找回保留数据所需的目录定位信息会保留。'),
            ('recovery', '删除未命名工作的恢复文件', '未保存的工作可能无法找回，请先确认不再需要。'),
        )
        for key, caption, description in rows:
            checkbox = QCheckBox(caption)
            checkbox.setEnabled(allow_cleanup)
            checkbox.setToolTip(description)
            self.choices[key] = checkbox
            layout.addWidget(checkbox)
            detail = QLabel(description)
            detail.setWordWrap(True)
            detail.setProperty('role', 'muted')
            detail.setContentsMargins(22, 0, 0, 0)
            layout.addWidget(detail)
        protection = QLabel('已保存的项目、原始影像和导出成果不会删除。无法确认归属的文件会保留。')
        protection.setWordWrap(True)
        layout.addWidget(protection)
        layout.addStretch(1)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_button = QPushButton('取消卸载')
        self.cancel_button.clicked.connect(self.reject)
        buttons.addWidget(self.cancel_button)
        self.continue_button = QPushButton('继续卸载')
        self.continue_button.setObjectName('primary')
        self.continue_button.setAutoDefault(False)
        self.continue_button.clicked.connect(self.accept)
        buttons.addWidget(self.continue_button)
        layout.addLayout(buttons)

    def selections(self):
        return {key: checkbox.isChecked() for key, checkbox in self.choices.items()}


def choose_uninstall_cleanup(resource_path='', parent=None, *, allow_cleanup=True, unavailable_reason=''):
    """Return None on cancellation or the four selected boolean options."""
    dialog = UninstallCleanupDialog(resource_path, parent, allow_cleanup=allow_cleanup, unavailable_reason=unavailable_reason)
    try:
        return dialog.selections() if dialog.exec() == QDialog.DialogCode.Accepted else None
    finally:
        dialog.deleteLater()


class _CleanupWorker(QThread):
    completed = Signal(object)

    def __init__(self, mask, cleanup, parent=None):
        super().__init__(parent)
        self.mask = mask
        self.cleanup = cleanup

    def run(self):
        try:
            self.completed.emit((self.cleanup(self.mask), ''))
        except Exception as error:
            self.completed.emit((None, _cleanup_error_text(error)))


def _cleanup_error_text(error):
    """Show actionable Chinese reasons without exposing raw tracebacks."""
    if isinstance(error, ValueError):
        message = ' '.join(str(error).split())[:400]
        if any('\u4e00' <= char <= '\u9fff' for char in message):
            return message
    if isinstance(error, OSError):
        if getattr(error, 'winerror', None) in (32, 33):return '文件正在使用，请关闭 GeoForma 后重试。'
        if getattr(error, 'winerror', None) == 5 or error.errno == 13:return '没有清理所选文件的权限。'
        if getattr(error, 'winerror', None) == 112 or error.errno == 28:return '磁盘空间不足，无法完成清理。'
        return '读取或清理文件时发生错误，请检查资源目录及磁盘状态。'
    return '清理过程中发生错误。'


class CleanupProgressDialog(QDialog):
    """Keep the event loop responsive while cleanup runs to completion."""
    def __init__(self, mask, cleanup, parent=None):
        super().__init__(parent)
        self.setWindowTitle('卸载 GeoForma')
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        label = QLabel('正在清理所选数据，请稍候。')
        label.setWordWrap(True)
        layout.addWidget(label)
        progress = QProgressBar()
        progress.setRange(0, 0)
        progress.setTextVisible(False)
        layout.addWidget(progress)
        self.outcome = None
        self.worker = _CleanupWorker(mask, cleanup, self)
        self.worker.completed.connect(self._completed)

    def _completed(self, outcome):
        self.outcome = outcome
        self.accept()

    def reject(self):
        # Esc and window-close must not interrupt a partially completed cleanup.
        if self.outcome is not None:super().reject()

    def closeEvent(self, event):
        if self.outcome is None:event.ignore()
        else:super().closeEvent(event)

    def execute(self):
        self.worker.start()
        try:
            self.exec()
            return self.outcome
        finally:
            self.worker.wait()
            self.deleteLater()
