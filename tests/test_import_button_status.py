import threading,time
import pytest
from PySide6.QtTest import QTest
from test_workbench import workbench,fake_image


@pytest.mark.parametrize('outcome',['success','failure','cancel'])
def test_import_button_keeps_label_while_status_bar_tracks_import(workbench,monkeypatch,outcome):
    from geoforma.controllers import images
    w,app,wait,errors=workbench;started=threading.Event();release=threading.Event();reports=[]
    def read(path):
        started.set();assert release.wait(5)
        if outcome=='failure':raise ValueError('invalid raster')
        return fake_image('slow',path)
    monkeypatch.setattr(images,'inspect_source',read)
    monkeypatch.setattr(images,'make_recipe',lambda *a:{'bands':[1,2,3]})
    w.show_import_report=lambda summary,details:reports.append(details)
    before=w.import_button.geometry()
    try:
        w.import_paths(['slow.tif'])
        assert not w.import_button.isEnabled() and w.import_button.text()=='导入影像'
        assert w.import_button.icon().isNull() and w.progress.model.state.phase=='running'
        deadline=time.monotonic()+3
        while not started.is_set():
            app.processEvents();QTest.qWait(2);assert time.monotonic()<deadline
        frame=w.import_button.grab().toImage()
        QTest.qWait(120);app.processEvents()
        assert w.import_button.grab().toImage()==frame
        assert w.state_label.text()=='导入影像' and w.progress.isVisible()
        assert w.import_button.geometry()==before
        if outcome=='cancel':w.cancel()
    finally:release.set()
    wait()
    assert w.import_button.isEnabled()
    assert w.import_button.text()=='导入影像' and w.import_button.geometry()==before
    assert len(w.project['images'])==(1 if outcome=='success' else 0)
    assert bool(reports)==(outcome=='failure')
    assert not errors
    assert w.progress.model.state.phase=={'cancel':'cancelled','failure':'failed','success':'complete'}[outcome]


def test_reference_import_keeps_button_label_and_status_bar_progress(workbench):
    w,app,wait,errors=workbench;started=threading.Event();release=threading.Event()
    def work(task):
        started.set();task.signals.progress.emit(1,2,'tile.tif');assert release.wait(5)
    try:
        w.run('导入参考：NDWI',work,lambda _:None,kind='reference_import')
        deadline=time.monotonic()+3
        while not started.is_set() or w.progress_count.text()!='参考 1 / 2':
            app.processEvents();QTest.qWait(2);assert time.monotonic()<deadline
        button=w.import_reference_button
        assert not button.isEnabled() and button.text()=='导入参考' and button.icon().isNull()
        frame=button.grab().toImage();QTest.qWait(120);app.processEvents()
        assert button.grab().toImage()==frame
        assert w.state_label.text()=='导入参考' and w.progress.isVisible()
    finally:release.set()
    wait()
    assert w.import_reference_button.isEnabled() and w.progress.model.state.phase=='complete' and not errors
