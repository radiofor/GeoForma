import sys
import importlib.metadata
from pathlib import Path
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QToolButton
from geoforma.application_info import DOCUMENTS,document_text,dependency_rows
from geoforma.ui.information import DocumentationDialog,DependencyVersionsDialog
from geoforma.distribution import VERSION
from test_workbench import workbench


def test_settings_remains_available_without_references_and_while_model_task_runs(workbench,monkeypatch):
    w,app,wait,errors=workbench
    assert w.settings_button.menu() is w.settings_menu and w.settings_button.isEnabled()
    expected=['资源配置','数据目录']
    assert [action.text() for action in w.settings_menu.actions() if not action.isSeparator()]==expected
    assert w.help_group.title()=='帮助与诊断'
    assert [button.text() for button in w.help_group.findChildren(QToolButton)]==['操作说明','任务记录','依赖库版本']
    assert w.reference_manage_button.defaultAction() is w.reference_manage_action
    assert w.reference_manage_button.parentWidget() is w.import_reference_button.parentWidget()
    assert not w.reference_manage_action.isEnabled()
    opened=[]
    monkeypatch.setattr(DocumentationDialog,'exec',lambda dialog:(opened.append(('docs',dialog.browser.toPlainText())) or 0))
    monkeypatch.setattr(DependencyVersionsDialog,'exec',lambda dialog:(opened.append(('versions',dict(dialog.rows))) or 0))
    w.task=object()
    try:
        w.update_controls();w.documentation_action.trigger();w.dependencies_action.trigger()
        assert w.settings_button.isEnabled() and not w.reference_manage_action.isEnabled()
        assert opened[0][0]=='docs' and '开始标注' in opened[0][1]
        assert opened[1][0]=='versions' and opened[1][1]['GeoForma']==VERSION
    finally:w.task=None;w.update_controls()
    assert not errors


def test_settings_actions_keep_data_directory_and_logs_separate(workbench,monkeypatch):
    from PySide6.QtGui import QDesktopServices
    from geoforma.domain import data_dir
    w,app,wait,errors=workbench;urls=[]
    monkeypatch.setattr(QDesktopServices,'openUrl',lambda url:(urls.append(url.toLocalFile()) or True))
    w.data_directory_action.trigger()
    assert [Path(url) for url in urls]==[data_dir()] and not w.log_dock.isVisible()
    w.task_log_action.trigger();assert w.log_dock.isVisible()
    w.task_log_action.trigger();assert not w.log_dock.isVisible()
    monkeypatch.setattr(QDesktopServices,'openUrl',lambda url:False)
    w.data_directory_action.trigger();assert '无法打开数据目录' in w.statusBar()._error_toast.label.text() and not errors


@pytest.mark.parametrize('lightweight',[False,True])
def test_settings_menu_is_consistent_for_both_installation_modes(monkeypatch,lightweight):
    from geoforma import native_runtime
    from geoforma.window import MainWindow
    monkeypatch.setattr(native_runtime,'lightweight',lambda:lightweight)
    app=QApplication.instance() or QApplication([]);window=MainWindow(auto_prepare=False)
    try:
        names=[action.text() for action in window.settings_menu.actions() if not action.isSeparator()]
        assert names==['资源配置','数据目录']
        if not lightweight:
            assert window.model_runtime.text().startswith('设备：')
            assert '模型加载后显示实际计算设备' in window.model_runtime.toolTip()
        assert window.reference_manage_action not in window.settings_menu.actions()
        assert window.documentation_action not in window.settings_menu.actions()
        assert window.dependencies_action not in window.settings_menu.actions()
    finally:window.dirty=False;window.close();app.processEvents()


def test_local_documents_and_versions_do_not_import_torch_and_copy_current_versions():
    app=QApplication.instance() or QApplication([]);before={name for name in sys.modules if name=='torch' or name.startswith('torch.')}
    dialog=DocumentationDialog()
    for index,(_,filename) in enumerate(DOCUMENTS):
        dialog.navigation.setCurrentRow(index)
        assert dialog.browser.toPlainText()==document_text(filename) and '未随程序提供' not in dialog.browser.toPlainText()
    versions=DependencyVersionsDialog();versions.copy_button.click()
    assert 'GeoForma\t'+VERSION in app.clipboard().text() and 'PyTorch\t'+importlib.metadata.version('torch') in app.clipboard().text()
    assert {'Requests','charset-normalizer','urllib3','IDNA'}<=dict(versions.rows).keys()
    assert before=={name for name in sys.modules if name=='torch' or name.startswith('torch.')}
    dialog.deleteLater();versions.deleteLater()
