"""Resource maintenance menu and explicit stop-before-close behavior."""
import threading
import time
from pathlib import Path
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from geoforma.ui.resources import ResourceDialog
from test_workbench import workbench


def test_resource_tabs_fill_row_equally_and_switch_at_resized_widths(workbench,monkeypatch):
    from geoforma import native_runtime
    w,app,wait,errors=workbench
    monkeypatch.setattr(native_runtime,'lightweight',lambda:True)
    dialog=ResourceDialog(w);dialog.show();app.processEvents()
    try:
        bar=dialog.tabs.tabBar()
        for width in (680,761,920,680,761):
            dialog.resize(width,620);app.processEvents()
            assert dialog.width()==width
            first,second=bar.tabRect(0),bar.tabRect(1)
            assert abs(first.width()-second.width())<=1
            assert first.left()==0 and second.left()==first.right()+1
            assert abs(second.right()+1-dialog.tabs.width())<=1
            QTest.mouseClick(bar,Qt.MouseButton.LeftButton,pos=second.center())
            assert dialog.tabs.currentIndex()==1
            QTest.mouseClick(bar,Qt.MouseButton.LeftButton,pos=first.center())
            assert dialog.tabs.currentIndex()==0
        assert not errors
    finally:dialog.accept();dialog.deleteLater()


def test_single_resource_tab_fills_row(workbench,monkeypatch):
    from geoforma import native_runtime
    w,app,wait,errors=workbench
    monkeypatch.setattr(native_runtime,'lightweight',lambda:False)
    dialog=ResourceDialog(w);dialog.show();app.processEvents()
    try:
        bar=dialog.tabs.tabBar()
        assert bar.count()==1 and abs(bar.tabRect(0).width()-dialog.tabs.width())<=1
        assert not errors
    finally:dialog.accept();dialog.deleteLater()


def process_until(app,condition):
    deadline=time.monotonic()+3
    while not condition() and time.monotonic()<deadline:
        app.processEvents();time.sleep(.002)
    assert condition()


def test_resource_location_is_visible_before_and_during_configuration(workbench,tmp_path,monkeypatch):
    w,app,wait,errors=workbench
    folder=tmp_path/'GeoForma-Resources';monkeypatch.setenv('GEOFORMA_DATA_DIR',str(folder))
    dialog=ResourceDialog(w);dialog.show();app.processEvents()
    started=threading.Event();release=threading.Event()
    def work(task):
        started.set();release.wait(5);return None
    try:
        assert dialog.location_path.isVisible()
        assert dialog.location_path.text()==str(folder)
        assert dialog.location_path._display_text
        assert dialog.location_choose.isEnabled()
        dialog.run('配置运行库',work);process_until(app,started.is_set)
        assert dialog.location_path.isVisible() and dialog.location_path.text()==str(folder)
        assert dialog.location_path._display_text
        assert not dialog.location_choose.isEnabled()
    finally:
        release.set();wait();dialog.accept();dialog.deleteLater()
    assert not errors


def test_maintenance_actions_are_in_more_menu_and_open_actual_data_folder(workbench,tmp_path,monkeypatch):
    from geoforma.ui import resources
    w,app,wait,errors=workbench
    folder=tmp_path/'用户资源';monkeypatch.setenv('GEOFORMA_DATA_DIR',str(folder))
    opened=[];monkeypatch.setattr(resources.QDesktopServices,'openUrl',lambda url:opened.append(url.toLocalFile()) or True)
    dialog=ResourceDialog(w);dialog.show();app.processEvents()
    try:
        assert dialog.more_button.menu() is dialog.more_menu
        assert [action.text() for action in dialog.more_menu.actions()]==['打开资源文件夹','清理旧运行库下载缓存']
        assert dialog.more_button.size()==dialog.stop_button.size()==dialog.close_button.size()
        assert not dialog.stop_button.isEnabled() and dialog.close_button.isEnabled()
        dialog.open_folder_action.trigger()
        assert len(opened)==1 and Path(opened[0])==folder and folder.is_dir()
        dialog.close_button.click();assert not dialog.isVisible() and not errors
    finally:dialog.accept();dialog.deleteLater()


@pytest.mark.parametrize('checks_cancel',[True,False],ids=['cooperative-stop','result-already-pending'])
def test_only_stop_can_cancel_and_close_waits_for_worker_exit(workbench,checks_cancel):
    w,app,wait,errors=workbench
    dialog=ResourceDialog(w);dialog.show();app.processEvents()
    initial=(dialog.size(),dialog.more_button.geometry(),dialog.stop_button.geometry(),dialog.close_button.geometry())
    started=threading.Event();release=threading.Event();results=[]
    def work(task):
        started.set();release.wait(5)
        if checks_cancel:task.check()
        return 'finished'
    try:
        dialog.run('配置运行库',work,results.append);process_until(app,started.is_set)
        owner=dialog.task
        assert owner is w.task and dialog.stop_button.isEnabled() and not dialog.close_button.isEnabled()
        assert not dialog.clear_cache_action.isEnabled() and dialog.open_folder_action.isEnabled()
        # X, Esc, accept/reject and the disabled footer close never request a stop.
        assert not dialog.close()
        QTest.keyClick(dialog,Qt.Key.Key_Escape)
        dialog.accept();dialog.reject();dialog.close_button.click();app.processEvents()
        assert dialog.isVisible() and not owner.cancel_event.is_set()
        assert dialog.timer.isActive() and '先停止' in dialog.close_button.toolTip()
        dialog.stop_button.click()
        assert owner.cancel_event.is_set() and dialog.phase.text()=='正在停止'
        assert not dialog.stop_button.isEnabled() and not dialog.close_button.isEnabled()
        assert not dialog.close() and dialog.isVisible()
        dialog.report(90,100,'迟到的进度');assert dialog.phase.text()=='正在停止'
        release.set();wait()
        assert dialog.task is None and dialog.progress.phase=='cancelled'
        assert dialog.phase.text()=='已停止' and w.progress.phase=='cancelled'
        assert dialog.close_button.isEnabled() and not dialog.stop_button.isEnabled()
        assert not results and not errors
        assert initial==(dialog.size(),dialog.more_button.geometry(),dialog.stop_button.geometry(),dialog.close_button.geometry())
        # A new configuration starts normally after stopping; no stale cancellation.
        dialog.run('重新配置',lambda task:'retry',results.append);wait()
        assert results==['retry'] and dialog.progress.phase=='complete' and dialog.close_button.isEnabled()
        dialog.stop();assert dialog.progress.phase=='complete'
        if checks_cancel:dialog.close_button.click()
        else:assert dialog.close()
        assert not dialog.isVisible()
    finally:
        release.set();wait();dialog.accept();dialog.deleteLater()


def test_failed_open_folder_keeps_dialog_usable_and_reports_reason(workbench,monkeypatch):
    from geoforma.ui import resources
    w,app,wait,errors=workbench;dialog=ResourceDialog(w)
    monkeypatch.setattr(resources.QDesktopServices,'openUrl',lambda url:False)
    try:
        dialog.open_folder_action.trigger()
        assert '无法打开资源文件夹' in dialog.details.toPlainText()
        assert dialog.close_button.isEnabled() and dialog.progress.phase=='idle' and not errors
    finally:dialog.accept();dialog.deleteLater()
