from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
import threading

from geoforma.ui.uninstall_cleanup import UninstallCleanupDialog, choose_uninstall_cleanup


def test_uninstall_choices_default_to_preserving_all_data():
    app = QApplication.instance() or QApplication([])
    dialog = UninstallCleanupDialog('F:/GeoForma-Resources')
    dialog.show(); app.processEvents()
    assert dialog.selections() == {'caches': False, 'models': False, 'settings': False, 'recovery': False}
    assert all(item.isEnabled() for item in dialog.choices.values())
    dialog.choices['caches'].click()
    dialog.choices['recovery'].click()
    assert dialog.selections() == {'caches': True, 'models': False, 'settings': False, 'recovery': True}
    dialog.reject(); dialog.deleteLater()


def test_uninstall_choice_returns_none_when_cancelled():
    app = QApplication.instance() or QApplication([])
    def cancel():
        dialog = app.activeModalWidget()
        dialog.choices['models'].click()
        dialog.cancel_button.click()
    QTimer.singleShot(0, cancel)
    assert choose_uninstall_cleanup('F:/GeoForma-Resources') is None


def test_unverified_user_cannot_select_cleanup():
    app = QApplication.instance() or QApplication([])
    def accept():
        dialog = app.activeModalWidget()
        assert not any(item.isEnabled() for item in dialog.choices.values())
        dialog.continue_button.click()
    QTimer.singleShot(0, accept)
    assert choose_uninstall_cleanup(allow_cleanup=False) == {'caches': False, 'models': False, 'settings': False, 'recovery': False}


def test_uninstall_command_encodes_selection_without_deleting_data(monkeypatch, tmp_path):
    from geoforma import uninstall_commands, uninstall_identity, uninstall_cleanup, resource_location
    from geoforma.ui import uninstall_cleanup as ui
    monkeypatch.setattr(uninstall_commands, '_application', lambda: None)
    monkeypatch.setattr(uninstall_identity, 'current_user_owns_desktop', lambda: True)
    monkeypatch.setattr(uninstall_cleanup, '_local_data_root', lambda: tmp_path)
    monkeypatch.setattr(resource_location, 'current_resource_dir', lambda root: root)
    monkeypatch.setattr(ui, 'choose_uninstall_cleanup', lambda *a, **k: {'caches': True, 'models': False, 'settings': True, 'recovery': False})
    monkeypatch.setattr(uninstall_cleanup, 'cleanup_selected', lambda *args: (_ for _ in ()).throw(AssertionError('selection must not clean')))
    assert uninstall_commands.choose() == 37


def test_uninstall_command_does_not_offer_cleanup_to_unverified_identity(monkeypatch):
    from geoforma import uninstall_commands, uninstall_identity
    from geoforma.ui import uninstall_cleanup as ui
    monkeypatch.setattr(uninstall_commands, '_application', lambda: None)
    monkeypatch.setattr(uninstall_identity, 'current_user_owns_desktop', lambda: False)
    kwargs = []
    monkeypatch.setattr(ui, 'choose_uninstall_cleanup', lambda *a, **k: kwargs.append(k) or None)
    assert uninstall_commands.choose() == 1
    assert kwargs[0]['allow_cleanup'] is False


def test_cleanup_progress_is_responsive_and_cannot_be_closed_while_running():
    from geoforma.ui.uninstall_cleanup import CleanupProgressDialog
    app = QApplication.instance() or QApplication([])
    release = threading.Event(); checks = []; identities = []
    def work(mask):
        identities.append(threading.get_ident()); release.wait(5)
        return {'skipped': [], 'mask': mask}
    dialog = CleanupProgressDialog(3, work)
    def inspect():
        dialog.reject(); closed = dialog.close()
        checks.append((dialog.isVisible(), closed))
        release.set()
    QTimer.singleShot(30, inspect)
    result, failed = dialog.execute()
    assert checks == [(True, False)]
    assert identities and identities[0] != threading.get_ident()
    assert not failed and result['mask'] == 3


def test_cleanup_progress_returns_failure_from_worker():
    from geoforma.ui.uninstall_cleanup import CleanupProgressDialog
    app = QApplication.instance() or QApplication([])
    def work(mask):raise OSError('模拟清理失败')
    assert CleanupProgressDialog(1, work).execute() == (None, '读取或清理文件时发生错误，请检查资源目录及磁盘状态。')


def test_cleanup_worker_preserves_chinese_reason_and_hides_unknown_exception_details():
    from geoforma.ui.uninstall_cleanup import _cleanup_error_text
    assert _cleanup_error_text(ValueError('资源迁移尚未完成，请先继续迁移。')) == '资源迁移尚未完成，请先继续迁移。'
    assert _cleanup_error_text(RuntimeError('internal detail')) == '清理过程中发生错误。'


def test_cleanup_failure_reports_specific_safe_chinese_reason_and_possible_partial_cleanup(monkeypatch):
    from geoforma import uninstall_commands
    from geoforma.ui import uninstall_cleanup as ui
    from PySide6.QtWidgets import QMessageBox
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(uninstall_commands, '_application', lambda: app)
    monkeypatch.setattr(uninstall_commands, '_current_resource_root', lambda: 'F:/GeoForma-Resources')
    monkeypatch.setattr(uninstall_commands, '_confirm_cleanup', lambda *args: True)
    monkeypatch.setattr(ui.CleanupProgressDialog, 'execute', lambda self: (None, '资源迁移尚未完成，请先完成迁移。'))
    messages = []
    monkeypatch.setattr(QMessageBox, 'exec', lambda self: messages.append(self.text()) or 0)
    assert uninstall_commands.cleanup(1) == 2
    assert '资源迁移尚未完成' in messages[0] and '只清理了一部分' in messages[0]


def test_cleanup_skipped_files_reports_resource_directory(monkeypatch):
    from geoforma import uninstall_commands
    from geoforma.ui import uninstall_cleanup as ui
    from PySide6.QtWidgets import QMessageBox
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(uninstall_commands, '_application', lambda: app)
    monkeypatch.setattr(uninstall_commands, '_current_resource_root', lambda: 'F:/GeoForma-Resources')
    monkeypatch.setattr(uninstall_commands, '_confirm_cleanup', lambda *args: True)
    monkeypatch.setattr(ui.CleanupProgressDialog, 'execute', lambda self: ({'skipped': ['保留文件'], 'root': 'F:/GeoForma-Resources'}, ''))
    messages = []
    monkeypatch.setattr(QMessageBox, 'exec', lambda self: messages.append(self.text()) or 0)
    assert uninstall_commands.cleanup(1) == 0
    assert 'F:/GeoForma-Resources' in messages[0] and '未全部完成' in messages[0]


def test_cancelling_cleanup_at_final_confirmation_preserves_data(monkeypatch):
    from geoforma import uninstall_commands, uninstall_cleanup
    monkeypatch.setattr(uninstall_commands, '_application', lambda: None)
    monkeypatch.setattr(uninstall_commands, '_current_resource_root', lambda: 'F:/GeoForma-Resources')
    checks = []
    monkeypatch.setattr(uninstall_commands, '_confirm_cleanup', lambda mask, root: checks.append((mask, root)) or False)
    monkeypatch.setattr(uninstall_cleanup, 'cleanup_selected', lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('must not clean')))
    assert uninstall_commands.cleanup(3) == 0
    assert checks == [(3, 'F:/GeoForma-Resources')]


def test_no_cleanup_and_settings_only_do_not_require_a_resource_directory(monkeypatch):
    from geoforma import uninstall_commands
    from geoforma.ui import uninstall_cleanup as ui
    monkeypatch.setattr(uninstall_commands, '_application', lambda: None)
    monkeypatch.setattr(uninstall_commands, '_current_resource_root', lambda: (_ for _ in ()).throw(AssertionError('must not resolve')))
    seen = []
    monkeypatch.setattr(uninstall_commands, '_confirm_cleanup', lambda mask, root: seen.append((mask, root)) or False)
    assert uninstall_commands.cleanup(0) == 0
    assert uninstall_commands.cleanup(4) == 0
    assert seen == [(4, None)]


def test_selected_resource_path_is_passed_to_locked_cleanup(monkeypatch):
    from geoforma import uninstall_commands, uninstall_cleanup
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(uninstall_commands, '_application', lambda: app)
    monkeypatch.setattr(uninstall_commands, '_current_resource_root', lambda: 'F:/GeoForma-Resources')
    monkeypatch.setattr(uninstall_commands, '_confirm_cleanup', lambda mask, root: True)
    seen = []
    monkeypatch.setattr(uninstall_cleanup, 'cleanup_selected', lambda mask, expected_root=None: seen.append((mask, expected_root)) or {'skipped': []})
    assert uninstall_commands.cleanup(2) == 0
    assert seen == [(2, 'F:/GeoForma-Resources')]
