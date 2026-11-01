"""Separate selection from cleanup so cancelled uninstalls preserve data."""
import os

_OPTIONS = ('caches', 'models', 'settings', 'recovery')
_CAPTIONS = ('影像缓存和日志', '模型权重和 PyTorch 运行库', '软件设置', '未命名工作的恢复文件')


def _application():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from .theme import install_theme
    install_theme(app)
    return app


def choose():
    from .ui.uninstall_cleanup import choose_uninstall_cleanup
    from .uninstall_identity import current_user_owns_desktop
    app = _application()
    # Never allow environment overrides to redirect uninstall cleanup.
    os.environ.pop('GEOFORMA_DATA_DIR', None)
    os.environ.pop('GEOFORMA_SETTINGS_FILE', None)
    try:
        allowed = bool(current_user_owns_desktop())
    except Exception:
        allowed = False
    path = ''
    if allowed:
        try:
            from .uninstall_cleanup import _local_data_root
            from .resource_location import current_resource_dir
            path = str(current_resource_dir(_local_data_root()))
        except (OSError, ValueError, RuntimeError):
            allowed = False
    reason = '' if allowed else '无法确认用户身份或资源目录，数据清理不可用。卸载时将保留数据。'
    choices = choose_uninstall_cleanup(path, allow_cleanup=allowed, unavailable_reason=reason)
    if choices is None:return 1
    return 32 + sum(1 << index for index, key in enumerate(_OPTIONS) if choices.get(key))


def _current_resource_root():
    from .uninstall_identity import current_user_owns_desktop
    from .uninstall_cleanup import _local_data_root
    from .resource_location import current_resource_dir
    if not current_user_owns_desktop():raise ValueError('无法确认当前账户与桌面用户一致，未清理任何数据。')
    return str(current_resource_dir(_local_data_root()))


def _confirm_cleanup(mask, root):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QMessageBox
    selected = '\n'.join('• ' + caption for index, caption in enumerate(_CAPTIONS) if mask & (1 << index))
    location = '当前资源目录：' + root if root else '本次仅清理软件设置，不涉及资源目录。'
    box = QMessageBox(QMessageBox.Icon.Warning, '确认清理数据', '', QMessageBox.StandardButton.NoButton)
    box.setTextFormat(Qt.TextFormat.PlainText)
    box.setText('将清理以下内容：\n' + selected + '\n\n' + location +
                '\n\n清理后相关数据无法恢复。选择保留数据仍会继续卸载程序。')
    remove = box.addButton('清理并继续卸载', QMessageBox.ButtonRole.AcceptRole)
    box.addButton('保留数据并继续卸载', QMessageBox.ButtonRole.RejectRole)
    box.exec()
    return box.clickedButton() is remove


def cleanup(mask):
    from PySide6.QtWidgets import QMessageBox
    from .uninstall_cleanup import cleanup_selected
    from .ui.uninstall_cleanup import CleanupProgressDialog
    app = _application()
    os.environ.pop('GEOFORMA_DATA_DIR', None)
    os.environ.pop('GEOFORMA_SETTINGS_FILE', None)
    if mask == 0:return 0
    def warning(text):
        box = QMessageBox(QMessageBox.Icon.Warning, '清理未完成', text, QMessageBox.StandardButton.Ok)
        box.button(QMessageBox.StandardButton.Ok).setText('确定')
        box.exec()
    try:
        root = _current_resource_root() if mask & 11 else None
    except Exception:
        warning('无法确认当前账户或资源目录，数据已保留。程序将继续卸载。')
        return 2
    if not _confirm_cleanup(mask, root):return 0
    outcome = CleanupProgressDialog(mask, lambda selection: cleanup_selected(selection, expected_root=root)).execute()
    if outcome is None or outcome[1]:
        reason = outcome[1] if outcome else '清理过程中发生错误。'
        warning(reason + '\n\n选中的数据可能只清理了一部分，请检查资源目录。')
        return 2
    if outcome[0].get('skipped'):
        root = str(outcome[0].get('root') or '未能获取')
        warning('部分内容无法确认归属或无法清理，已保留，清理未全部完成。\n\n资源目录：' + root)
    return 0
