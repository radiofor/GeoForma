import os,time,threading
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtCore import QTimer,Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QMessageBox
from geoforma.window import MainWindow
from geoforma.ui.progress_bar import COMPLETION_HOLD_MS


def wait(app,condition):
    deadline=time.monotonic()+4
    while not condition() and time.monotonic()<deadline:app.processEvents();time.sleep(.002)
    assert condition()


def test_model_cleanup_runs_off_ui_thread_and_animation_remains_responsive(tmp_path,monkeypatch):
    monkeypatch.setenv('GEOFORMA_DATA_DIR',str(tmp_path/'data'))
    app=QApplication.instance() or QApplication([]);w=MainWindow(auto_prepare=False);w.dirty=False;w.show()
    started=threading.Event();release=threading.Event();thread_ids=[];w.service.process=object()
    def close():
        thread_ids.append(threading.get_ident());started.set();release.wait(3);w.service.process=None
    w.service.close=close
    ticks=[];timer=QTimer();timer.setInterval(5);timer.timeout.connect(lambda:ticks.append(True));timer.start()
    try:
        assert not w.close();wait(app,started.is_set)
        assert w.shutdown_dialog.isVisible() and w.shutdown_dialog.progress.maximum()==3 and w.shutdown_dialog.progress.value()==2
        assert '释放模型' in w.shutdown_dialog.phase_label.text()
        QTest.keyClick(w.shutdown_dialog,Qt.Key.Key_Escape);assert w.shutdown_dialog.isVisible()
        # Windows can coalesce short timers. Verify fresh GUI heartbeats while
        # cleanup is blocked, without assuming a 5 ms scheduling resolution.
        baseline=len(ticks);deadline=time.monotonic()+.5
        while len(ticks)-baseline<6 and time.monotonic()<deadline:QTest.qWait(10)
        assert len(ticks)-baseline>=6 and thread_ids[0]!=threading.get_ident() and not release.is_set()
        completed=[];w.shutdown_dialog.progress.completionPainted.connect(lambda:completed.append((time.monotonic(),w.isVisible(),w.shutdown_dialog.isVisible(),w.shutdown_complete)))
        release.set();wait(app,lambda:w.shutdown_complete and w.shutdown_task is None and not w.isVisible())
        assert completed and completed[0][1:]==(True,True,False) and time.monotonic()-completed[0][0]>=COMPLETION_HOLD_MS*.75/1000
        assert not w.shutdown_dialog.isVisible()
        assert w.shutdown_dialog.progress.model.state.phase=='complete'
    finally:
        release.set();timer.stop();wait(app,lambda:w.shutdown_task is None);w.dirty=False;w.close();app.processEvents()


def test_task_wait_phase_is_visible_and_exit_finishes_after_cancellation(tmp_path,monkeypatch):
    monkeypatch.setenv('GEOFORMA_DATA_DIR',str(tmp_path/'data'))
    app=QApplication.instance() or QApplication([]);w=MainWindow(auto_prepare=False);w.autosave=lambda:None;w.error=lambda message:None;w.show()
    started=threading.Event();release=threading.Event()
    def work(task):started.set();release.wait(3);task.check()
    w.run('test',work,lambda value:None);wait(app,started.is_set)
    try:
        w.close();assert w.closing and w.shutdown_dialog.isVisible()
        assert '结束后台' in w.shutdown_dialog.phase_label.text() and w.task.cancel_event.is_set()
        release.set();wait(app,lambda:w.shutdown_complete and not w.isVisible())
    finally:
        release.set();wait(app,lambda:w.task is None);w.dirty=False;w.close();app.processEvents()


def test_failed_autosave_dismisses_exit_feedback_and_keeps_work(tmp_path,monkeypatch):
    monkeypatch.setenv('GEOFORMA_DATA_DIR',str(tmp_path/'data'))
    import geoforma.controllers.projects as projects
    app=QApplication.instance() or QApplication([]);w=MainWindow(auto_prepare=False);w.show();w.project['images']=[{'id':'image','path':'source.tif'}];w.mark_dirty()
    started=threading.Event();release=threading.Event();warnings=[]
    def save(*args):started.set();release.wait(3);raise OSError('test disk error')
    monkeypatch.setattr(projects,'save_project',save);monkeypatch.setattr(QMessageBox,'warning',lambda *args:warnings.append(args))
    try:
        w.close();wait(app,started.is_set);assert w.shutdown_dialog.isVisible() and '保存' in w.shutdown_dialog.phase_label.text()
        feedback=w.shutdown_dialog
        release.set();wait(app,lambda:w.autosave_task is None)
        assert warnings and not w.closing and w.shutdown_dialog is None and w.isVisible() and w.dirty
        assert feedback.progress.model.state.phase=='failed'
    finally:
        release.set();wait(app,lambda:w.autosave_task is None);w.project_saves.pending.clear();w.project_saves.failed.clear();w.dirty=False;w.close();app.processEvents()


def test_idle_exit_needs_no_waiting_dialog(tmp_path,monkeypatch):
    monkeypatch.setenv('GEOFORMA_DATA_DIR',str(tmp_path/'data'))
    app=QApplication.instance() or QApplication([]);w=MainWindow(auto_prepare=False);w.dirty=False
    assert w.close() and w.shutdown_complete and w.shutdown_dialog is None
    app.processEvents()


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


def test_shutdown_stages_never_move_backward_and_aborting_cancels_completion_callback():
    from PySide6.QtWidgets import QWidget
    from geoforma.ui.shutdown_dialog import ShutdownDialog
    app=QApplication.instance() or QApplication([]);parent=QWidget();parent.show();step=[0]
    dialog=ShutdownDialog(parent,lambda:'test cleanup',lambda:step[0]);dialog.show();app.processEvents()
    try:
        assert dialog.progress.model.state.current==0 and dialog.progress.maximum()==3
        for current,expected in ((1,1),(2,2),(0,2)):
            step[0]=current;dialog.timer.timeout.emit()
            assert dialog.progress.model.state.current==expected
        callbacks=[];dialog.finish(on_finished=lambda:callbacks.append(True))
        wait(app,dialog.completion_timer.isActive)
        assert dialog.isVisible() and dialog.progress.display_fraction==1. and not callbacks
        dialog.finish('failed');QTest.qWait(COMPLETION_HOLD_MS+100);app.processEvents()
        assert not callbacks and not dialog.isVisible() and not dialog.completion_timer.isActive()
    finally:dialog.finish('failed');dialog.deleteLater();parent.close();app.processEvents()
