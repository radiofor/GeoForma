"""Reshape failures remain visible in the single status message area."""
import copy
from shapely.geometry import LineString,mapping

from test_reshape import OUT,raster_image,workbench
from test_reshape_auto import wait
from test_smoothing import settled


def test_no_crossing_reports_reason_in_status_bar(workbench):
    w,app,_=workbench;w.smooth_enabled.setChecked(False);settled(w,app)
    before=copy.deepcopy(w.project['labels']);w.begin_reshape(auto=True)
    for point in ((50,50),(60,60)):w.add_reshape_point(*point)
    w.finish_reshape();wait(w,app);app.processEvents()
    assert w.project['labels']==before and w.reshape_session is not None
    assert w.statusBar().currentMessage()=='重塑线未穿过标注边界，请调整编辑线。'
    assert w.statusBar().text_slot.currentWidget() is w.statusBar().notice


def test_worker_error_reports_reason_without_overwriting_annotation(workbench,monkeypatch):
    from geoforma import reshape
    w,app,_=workbench;w.smooth_enabled.setChecked(False);settled(w,app)
    before=copy.deepcopy(w.project['labels']);w.begin_reshape(auto=True)
    for point in OUT:w.add_reshape_point(*point)
    def fail(*args,**kwargs):raise ValueError('小数边界与编辑线无法安全匹配，请调整编辑线。')
    monkeypatch.setattr(reshape,'reshape_geometry',fail)
    w.finish_reshape();wait(w,app);app.processEvents()
    assert w.project['labels']==before and w.reshape_session is not None
    assert '小数边界与编辑线无法安全匹配' in w.statusBar().currentMessage()
    assert w.statusBar().text_slot.currentWidget() is w.statusBar().notice


def test_invalid_result_reports_reason_in_status_bar(workbench):
    w,app,_=workbench;w.smooth_enabled.setChecked(False);settled(w,app)
    label=copy.deepcopy(w.project['labels'][0]);w.begin_reshape(auto=True)
    result={'geometry':mapping(LineString([(0,0),(1,1)])),'stroke':OUT,
            'alternate':False,'window':[0,0,2,2],'added_pixels':0,'removed_pixels':0}
    w.apply_reshape_results(w.reshape_session,[('label',label)],[result]);app.processEvents()
    assert w.project['labels'][0]==label and w.reshape_session is not None
    assert w.statusBar().currentMessage() and w.statusBar().text_slot.currentWidget() is w.statusBar().notice
