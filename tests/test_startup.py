"""Bootstrap responsiveness, ownership, cancellation and failure recovery."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import threading
import time
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QThread, QTimer
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtTest import QTest
from geoforma.startup import StartupController, StartupWorker, prepare_startup
from geoforma.theme import install_theme
from geoforma.ui.progress_bar import COMPLETION_HOLD_MS


def spin(app, condition):
    start = time.monotonic()
    while not condition():
        app.processEvents()
        time.sleep(.002)
        if time.monotonic() - start > 10:
            raise TimeoutError('Startup did not settle')
    app.processEvents()


@pytest.fixture
def app(monkeypatch, tmp_path):
    value = QApplication.instance() or QApplication([])
    install_theme(value)
    monkeypatch.setattr(value, 'quit', lambda: None)
    monkeypatch.setenv('GEOFORMA_DATA_DIR', str(tmp_path))
    return value


def dispose(controller, app):
    assert controller.worker is None
    if controller.window:
        controller.window.close()
    controller.splash.allow_close = True
    controller.splash.close()
    controller.deleteLater()
    app.processEvents()


def test_splash_is_responsive_and_widgets_are_created_on_gui_thread(app):
    release = threading.Event()
    entered = threading.Event()
    observed = {}
    def prepare(progress, check):
        observed['worker_thread'] = QThread.currentThread()
        entered.set()
        progress(2, '读取应用配置')
        while not release.wait(.002):
            check()
        return 'prepared'
    def factory(context):
        observed.update(gui_thread=QThread.currentThread(), context=context)
        return QWidget()
    c = StartupController(app, prepare=prepare, window_factory=factory)
    ready = []
    c.ready.connect(ready.append)
    c.start()
    spin(app, entered.is_set)
    pulses = []
    timer = QTimer()
    timer.setInterval(1)
    timer.timeout.connect(lambda: pulses.append(True))
    timer.start()
    spin(app, lambda: len(pulses) >= 5 and c.splash.progress.value() == 2)
    assert c.splash.isVisible() and c.window is None
    release.set()
    spin(app, lambda: bool(ready))
    timer.stop()
    assert observed['worker_thread'] != app.thread()
    assert observed['gui_thread'] == app.thread() and observed['context'] == 'prepared'
    assert c.window.isVisible() and not c.splash.isVisible()
    assert c.splash.progress.model.state.phase=='complete'
    dispose(c, app)


def test_close_waits_for_worker_cancellation_without_building_window(app):
    entered = threading.Event()
    def prepare(progress, check):
        entered.set()
        while True:
            time.sleep(.002)
            check()
    c = StartupController(app, prepare=prepare, window_factory=lambda _: pytest.fail('Cancelled startup must not create widgets'))
    cancelled = []
    c.cancelled.connect(lambda: cancelled.append(True))
    c.start()
    spin(app, entered.is_set)
    c.splash.close()
    spin(app, lambda: bool(cancelled))
    assert c.worker is None and not c.splash.isVisible()
    assert c.splash.progress.model.state.phase=='cancelled'
    dispose(c, app)


def test_failed_preparation_can_retry_and_uses_no_partial_context(app):
    attempts = []
    def prepare(progress, check):
        attempts.append(True)
        if len(attempts) == 1:
            raise OSError('test initialization failure')
        return 'complete'
    built = []
    def factory(context):
        built.append(context)
        return QWidget()
    c = StartupController(app, prepare=prepare, window_factory=factory)
    errors, ready = [], []
    c.failed.connect(errors.append)
    c.ready.connect(ready.append)
    c.start()
    spin(app, lambda: bool(errors))
    assert not built and c.splash.error_row.isVisible() and c.worker is None
    assert c.splash.progress.model.state.phase=='failed'
    c.splash.retry.click()
    spin(app, lambda: bool(ready))
    assert built == ['complete'] and len(attempts) == 2
    dispose(c, app)


def test_widget_creation_failure_remains_reviewable_and_can_close(app):
    def factory(_):
        raise RuntimeError('test widget initialization failure')
    c = StartupController(app, prepare=lambda *a: 'complete', window_factory=factory)
    errors, cancelled = [], []
    c.failed.connect(errors.append)
    c.cancelled.connect(lambda: cancelled.append(True))
    c.start()
    spin(app, lambda: bool(errors))
    assert 'test widget initialization failure' in c.splash.details
    c.splash.close()
    spin(app, lambda: bool(cancelled))
    dispose(c, app)


def test_real_bootstrap_checks_storage_and_coordinates_without_loading_torch(tmp_path, monkeypatch, app):
    monkeypatch.setenv('GEOFORMA_DATA_DIR', str(tmp_path))
    # Import guards ensure bootstrap never resolves a model backend or Torch.
    import builtins
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name == 'torch' or name.startswith('torch.') or name == 'backend':
            pytest.fail('Model must remain lazy during application startup')
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', guarded)
    worker = StartupWorker()
    worker.start()
    spin(app, lambda: not worker.isRunning())
    assert not worker.error and worker.result.data_root == tmp_path
    assert worker.result.project['model']['backend'] == 'sam2.1'
    assert worker.result.project['model']['variant'] == 'small'
    assert (tmp_path / 'recovery').is_dir() and not list(tmp_path.glob('tmp*'))
    window = worker.result.window_type(auto_prepare=False, startup_context=worker.result)
    window.autosave_timer.stop()
    assert window.project == worker.result.project and window.project is not worker.result.project
    window.project['model']['device'] = 'cpu'
    assert worker.result.project['model']['device'] == 'cuda'
    window.dirty = False
    window.close()
    app.processEvents()


def test_hardware_detection_runs_in_parallel_and_finishes_before_context(app,monkeypatch):
    from geoforma import runtime_hardware
    started=threading.Event();release=threading.Event();phases=[]
    def detect():
        started.set()
        assert release.wait(5)
        return {'nvidia':['test GPU']}
    monkeypatch.setattr(runtime_hardware,'detect_hardware',detect)
    worker=StartupWorker()
    def phase(index,text):
        phases.append(index)
        if index==4:
            assert started.is_set()
            release.set()
    worker.progress.connect(phase)
    try:
        worker.start();spin(app,lambda:not worker.isRunning())
        assert not worker.error and phases==[1,2,3,4]
        assert worker.result.runtime_hardware=={'nvidia':['test GPU']}
    finally:release.set();worker.wait()


def test_hardware_probe_wait_is_cancellable(monkeypatch):
    from geoforma import runtime_hardware
    from geoforma.startup import StartupCancelled
    release=threading.Event();started=threading.Event()
    def detect():
        started.set();release.wait(5);return {}
    monkeypatch.setattr(runtime_hardware,'detect_hardware',detect)
    probe=runtime_hardware.HardwareProbe();assert started.wait(2)
    try:
        with pytest.raises(StartupCancelled):probe.result(lambda:(_ for _ in ()).throw(StartupCancelled()))
    finally:release.set()


def test_unwritable_data_root_fails_before_widget_import(tmp_path, monkeypatch, app):
    file = tmp_path / 'not_a_directory'
    file.write_text('keep')
    monkeypatch.setenv('GEOFORMA_DATA_DIR', str(file))
    worker = StartupWorker()
    worker.start()
    spin(app, lambda: not worker.isRunning())
    assert worker.error and worker.result is None and file.read_text() == 'keep'


def test_fast_startup_keeps_workbench_hidden_until_full_frame_and_completion_pause(app):
    def prepare(progress,check):
        for phase in range(1,5):progress(phase,'test stage')
        return 'ready'
    controller=StartupController(app,prepare=prepare,window_factory=lambda _:QWidget())
    painted=[];ready=[]
    controller.splash.progress.completionPainted.connect(lambda:painted.append((time.monotonic(),controller.splash.isVisible(),controller.window.isVisible(),controller.splash.progress.display_fraction)))
    controller.ready.connect(lambda window:ready.append(time.monotonic()))
    controller.start();spin(app,lambda:bool(ready))
    assert painted and painted[0][1:]==(True,False,1.)
    assert ready[0]-painted[0][0]>=COMPLETION_HOLD_MS*.75/1000 and controller.splash.status.text()=='启动完成'
    assert controller.window.isVisible() and not controller.splash.isVisible();dispose(controller,app)


def test_cancel_during_completion_pause_cannot_reveal_a_late_workbench(app):
    controller=StartupController(app,prepare=lambda *args:'ready',window_factory=lambda _:QWidget())
    ready=[];cancelled=[];controller.ready.connect(ready.append);controller.cancelled.connect(lambda:cancelled.append(True))
    controller.splash.progress.completionPainted.connect(controller.cancel)
    controller.start();spin(app,lambda:bool(cancelled));QTest.qWait(COMPLETION_HOLD_MS+100);app.processEvents()
    assert not ready and not controller.window.isVisible() and not controller.reveal_timer.isActive()
    dispose(controller,app)


def test_real_workbench_defers_project_and_resource_dialog_until_revealed(app):
    from geoforma.window import MainWindow
    from geoforma.domain import new_project
    calls=[]
    class Window(MainWindow):
        def request_project_open(self,*args):calls.append('project')
        def remind_resources(self):calls.append('resources')
    context=SimpleNamespace(project=new_project(),runtime_hardware={})
    window=Window('test.gfm',startup_context=context);window.autosave=lambda:None
    QTest.qWait(450);assert not calls and not window.isVisible()
    window.show();spin(app,lambda:len(calls)==2);assert calls==['project','resources']
    window.dirty=False;window.close();app.processEvents()
