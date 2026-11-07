import os,time,threading
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtCore import QTimer,Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QMessageBox
from geoforma.window import MainWindow


def wait(app,condition):
    deadline=time.monotonic()+4
    while not condition() and time.monotonic()<deadline:app.processEvents();time.sleep(.002)
    assert condition()


def test_model_cleanup_runs_off_ui_thread_and_status_remains_responsive(tmp_path,monkeypatch):
    monkeypatch.setenv('GEOFORMA_DATA_DIR',str(tmp_path/'data'))
    app=QApplication.instance() or QApplication([]);w=MainWindow(auto_prepare=False);w.dirty=False;w.show()
    started=threading.Event();release=threading.Event();thread_ids=[];w.service.process=object()
    def close():
        thread_ids.append(threading.get_ident());started.set();release.wait(3);w.service.process=None
    w.service.close=close
    ticks=[];timer=QTimer();timer.setInterval(5);timer.timeout.connect(lambda:ticks.append(True));timer.start()
    try:
        assert not w.close();wait(app,started.is_set)
        assert w.closing and not hasattr(w,'shutdown_dialog')
        # Windows can coalesce short timers. Verify fresh GUI heartbeats while
        # cleanup is blocked, without assuming a 5 ms scheduling resolution.
        baseline=len(ticks);deadline=time.monotonic()+.5
        while len(ticks)-baseline<6 and time.monotonic()<deadline:QTest.qWait(10)
        assert len(ticks)-baseline>=6 and thread_ids[0]!=threading.get_ident() and not release.is_set()
        release.set();wait(app,lambda:w.shutdown_complete and w.shutdown_task is None and not w.isVisible())
    finally:
        release.set();timer.stop();wait(app,lambda:w.shutdown_task is None);w.dirty=False;w.close();app.processEvents()


def test_task_wait_phase_is_visible_and_exit_finishes_after_cancellation(tmp_path,monkeypatch):
    monkeypatch.setenv('GEOFORMA_DATA_DIR',str(tmp_path/'data'))
    app=QApplication.instance() or QApplication([]);w=MainWindow(auto_prepare=False);w.autosave=lambda:None;w.error=lambda message:None;w.show()
    started=threading.Event();release=threading.Event()
    def work(task):started.set();release.wait(3);task.check()
    w.run('test',work,lambda value:None);wait(app,started.is_set)
    try:
        w.close();assert w.closing
        assert w.task.cancel_event.is_set() and not hasattr(w,'shutdown_dialog')
        release.set();wait(app,lambda:w.shutdown_complete and not w.isVisible())
    finally:
        release.set();wait(app,lambda:w.task is None);w.dirty=False;w.close();app.processEvents()


def test_failed_autosave_dismisses_exit_feedback_and_keeps_work(tmp_path,monkeypatch):
    monkeypatch.setenv('GEOFORMA_DATA_DIR',str(tmp_path/'data'))
    import geoforma.controllers.projects as projects
    app=QApplication.instance() or QApplication([]);w=MainWindow(auto_prepare=False);w.show();w.project['images']=[{'id':'image','path':'source.tif'}];w.mark_dirty()
    started=threading.Event();release=threading.Event()
    def save(*args,**kwargs):started.set();release.wait(3);raise OSError('test disk error')
    monkeypatch.setattr(projects,'save_project',save)
    try:
        w.close();wait(app,started.is_set)
        release.set();wait(app,lambda:w.autosave_task is None)
        assert w.statusBar()._error_toast.label.isVisible() and 'test disk error' in w.statusBar()._error_toast.label.text()
        assert not w.closing and not hasattr(w,'shutdown_dialog') and w.isVisible() and w.dirty
    finally:
        release.set();wait(app,lambda:w.autosave_task is None);w.project_saves.pending.clear();w.project_saves.failed.clear();w.dirty=False;w.close();app.processEvents()


def test_idle_exit_needs_no_waiting_dialog(tmp_path,monkeypatch):
    monkeypatch.setenv('GEOFORMA_DATA_DIR',str(tmp_path/'data'))
    app=QApplication.instance() or QApplication([]);w=MainWindow(auto_prepare=False);w.dirty=False
    assert w.close() and w.shutdown_complete and not hasattr(w,'shutdown_dialog')
    app.processEvents()


def test_immediate_autosave_refusal_keeps_window_and_dirty_work(tmp_path,monkeypatch):
    monkeypatch.setenv('GEOFORMA_DATA_DIR',str(tmp_path/'data'))
    app=QApplication.instance() or QApplication([]);w=MainWindow(auto_prepare=False);w.show()
    w.dirty=True
    def refuse():w.statusBar().report_error('自动保存未完成');return False
    monkeypatch.setattr(w,'autosave',refuse)
    assert not w.close() and w.isVisible() and w.dirty and not w.closing
    assert w.statusBar()._error_toast.label.isVisible()
    monkeypatch.setattr(w,'autosave',lambda:None);w.dirty=False;w.close();app.processEvents()


def test_quick_background_shutdown_finishes_without_feedback(tmp_path,monkeypatch):
    monkeypatch.setenv('GEOFORMA_DATA_DIR',str(tmp_path/'data'))
    app=QApplication.instance() or QApplication([]);w=MainWindow(auto_prepare=False);w.dirty=False;w.show()
    w.service.process=object()
    def close():w.service.process=None
    w.service.close=close
    assert not w.close()
    wait(app,lambda:w.shutdown_complete and not w.isVisible())
    assert not hasattr(w,'shutdown_dialog')
    QTest.qWait(350);app.processEvents()
    assert not hasattr(w,'shutdown_dialog')


def test_quick_save_closes_without_feedback_after_data_is_written(tmp_path,monkeypatch):
    from geoforma.storage import save_project,load_project
    monkeypatch.setenv('GEOFORMA_DATA_DIR',str(tmp_path/'data'))
    app=QApplication.instance() or QApplication([]);w=MainWindow(auto_prepare=False);w.show()
    path=tmp_path/'project.gfm';save_project(w.project,path);w.project_path=path
    w.project['classes'][0]['name']='退出前编辑';w.mark_dirty()
    assert not w.close()
    wait(app,lambda:w.shutdown_complete and not w.isVisible())
    assert not hasattr(w,'shutdown_dialog') and load_project(path)['classes'][0]['name']=='退出前编辑'


def test_quick_exit_prevents_delayed_resource_reminder(tmp_path,monkeypatch):
    from geoforma import native_runtime
    from geoforma.controllers import resources
    monkeypatch.setenv('GEOFORMA_DATA_DIR',str(tmp_path/'data'))
    monkeypatch.setattr(native_runtime,'lightweight',lambda:True)
    monkeypatch.setattr(resources,'snapshot',lambda config:{'ready':False})
    app=QApplication.instance() or QApplication([]);w=MainWindow(auto_prepare=True);w.dirty=False;w.show()
    assert w.close() and w.shutdown_complete and w.closing
    QTest.qWait(450);app.processEvents()
    assert getattr(w,'resource_dialog',None) is None
    w.deleteLater()


def test_exit_closes_open_resource_dialog_without_starting_preparation(tmp_path,monkeypatch):
    from geoforma.controllers import resources
    from shiboken6 import isValid
    monkeypatch.setenv('GEOFORMA_DATA_DIR',str(tmp_path/'data'))
    monkeypatch.setattr(resources,'snapshot',lambda config:{'ready':True})
    app=QApplication.instance() or QApplication([]);w=MainWindow(auto_prepare=False);w.dirty=False;w.show()
    preparations=[];monkeypatch.setattr(w,'queue_preparation',lambda *args,**kwargs:preparations.append(True))
    w.configure_resources();app.processEvents();dialog=w.resource_dialog
    assert dialog is not None and dialog.isVisible()
    assert w.close() and w.shutdown_complete and w.closing
    app.processEvents()
    assert w.resource_dialog is None and (not isValid(dialog) or not dialog.isVisible()) and not preparations
    w.deleteLater()


def test_exit_waits_for_resource_task_before_closing_its_dialog(tmp_path,monkeypatch):
    from shiboken6 import isValid
    monkeypatch.setenv('GEOFORMA_DATA_DIR',str(tmp_path/'data'))
    app=QApplication.instance() or QApplication([]);w=MainWindow(auto_prepare=False);w.dirty=False;w.show()
    started=threading.Event();release=threading.Event()
    w.configure_resources();dialog=w.resource_dialog
    def work(task):started.set();release.wait(3);task.check()
    dialog.run('配置测试资源',work);wait(app,started.is_set)
    try:
        assert not w.close() and w.closing and dialog.isVisible()
        assert dialog.task.cancel_event.is_set()
        release.set();wait(app,lambda:w.shutdown_complete and not w.isVisible())
        assert w.resource_dialog is None and (not isValid(dialog) or not dialog.isVisible())
    finally:
        release.set();wait(app,lambda:w.task is None);w.dirty=False;w.close();app.processEvents();w.deleteLater()


