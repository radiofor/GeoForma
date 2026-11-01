import threading,time
import pytest
from PySide6.QtTest import QTest
from test_workbench import workbench,fake_image


@pytest.mark.parametrize('outcome',['success','failure','cancel'])
def test_import_animation_lifecycle_and_stable_geometry(workbench,monkeypatch,outcome):
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
        assert w.import_button.busy and w.import_button.timer.isActive() and not w.import_button.isEnabled()
        deadline=time.monotonic()+3
        while not started.is_set():
            app.processEvents();QTest.qWait(2);assert time.monotonic()<deadline
        frame=w.import_button.grab().toImage();angle=w.import_button.angle
        QTest.qWait(120);app.processEvents()
        assert w.import_button.angle!=angle and w.import_button.grab().toImage()!=frame
        assert w.import_button.geometry()==before
        if outcome=='cancel':w.cancel()
    finally:release.set()
    wait()
    assert not w.import_button.busy and not w.import_button.timer.isActive() and w.import_button.isEnabled()
    assert w.import_button.text()=='导入影像' and w.import_button.geometry()==before
    assert len(w.project['images'])==(1 if outcome=='success' else 0)
    assert bool(reports)==(outcome=='failure')
    assert not errors
    assert w.progress.model.state.phase=={'cancel':'cancelled','failure':'failed','success':'complete'}[outcome]
