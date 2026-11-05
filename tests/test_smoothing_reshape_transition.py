"""Reshape transitions never expose raw geometry while smoothing is enabled."""
import threading,time

import pytest
from PySide6.QtTest import QTest
from shapely.geometry import MultiPolygon,box,mapping,shape

from test_reshape import OUT,workbench,raster_image,prepare_preview
from test_smoothing import settled


def wait_until(app,predicate):
    deadline=time.monotonic()+10
    while not predicate():
        app.processEvents();QTest.qWait(2);assert time.monotonic()<deadline


def delay_smoothing(monkeypatch):
    from geoforma.controllers import smoothing
    original=smoothing.smooth_batch;started=threading.Event();release=threading.Event()
    def delayed(labels,value,image,task,cache=None):
        started.set()
        while not release.wait(.005):task.check()
        return original(labels,value,image,task,cache)
    monkeypatch.setattr(smoothing,'smooth_batch',delayed)
    return started,release


@pytest.mark.parametrize('target',['saved','draft'])
def test_reshape_keeps_previous_smooth_outline_until_new_result(workbench,monkeypatch,target):
    w,app,_=workbench
    if target=='draft':
        w.project['labels']=[];w.selected_id=None;w.selected_ids.clear()
        w.draft={'geometry':mapping(box(20,20,30,30)),'points':[],'pending':False}
    w.smooth_enabled.setChecked(True);w.refresh_labels();settled(w,app)
    key='target' if target=='saved' else '__draft';item=w.view.overlay_records[key];previous=item.geometry_value
    source=w.project['labels'][0]['geometry'] if target=='saved' else w.draft['geometry']
    assert not shape(previous).equals(shape(source))
    started,release=delay_smoothing(monkeypatch)
    try:
        w.begin_reshape(auto=True)
        for x,y in OUT:w.add_reshape_point(x,y)
        w.finish_reshape();wait_until(app,lambda:w.task is None)
        current=w.project['labels'][0]['geometry'] if target=='saved' else w.draft['geometry']
        assert not shape(current).equals(shape(source))
        assert w.view.overlay_records[key] is item and item.geometry_value is previous
        wait_until(app,started.is_set)
        assert item.geometry_value is previous and item.geometry_value is not current
    finally:
        release.set();settled(w,app)
    assert item.geometry_value is not current
    assert not shape(item.geometry_value).equals(shape(current))


def test_disabling_smoothing_during_reshape_transition_shows_exact_source(workbench,monkeypatch):
    w,app,_=workbench;w.smooth_enabled.setChecked(True);w.refresh_labels();settled(w,app)
    started,release=delay_smoothing(monkeypatch)
    try:
        w.begin_reshape(auto=True)
        for x,y in OUT:w.add_reshape_point(x,y)
        w.finish_reshape();wait_until(app,lambda:w.task is None);wait_until(app,started.is_set)
        source=w.project['labels'][0]['geometry'];w.smooth_enabled.setChecked(False);app.processEvents()
        assert w.view.overlay_records['target'].geometry_value is source
    finally:
        release.set();settled(w,app)
    assert w.view.overlay_records['target'].geometry_value is source


def test_reshape_without_smoothing_shows_new_source_immediately(workbench):
    w,app,_=workbench;w.smooth_enabled.setChecked(False);w.refresh_labels()
    w.begin_reshape(auto=True)
    for x,y in OUT:w.add_reshape_point(x,y)
    w.finish_reshape();wait_until(app,lambda:w.task is None)
    assert w.view.overlay_records['target'].geometry_value is w.project['labels'][0]['geometry']


def test_uncommitted_result_does_not_temporarily_replace_smooth_outline(workbench):
    w,app,_=workbench;w.smooth_enabled.setChecked(True);w.refresh_labels();settled(w,app)
    item=w.view.overlay_records['target'];previous=item.geometry_value
    prepare_preview(w);w.redraw()
    assert w.view.overlay_records['target'] is item and item.geometry_value is previous


def test_undo_during_smoothing_keeps_the_display_smooth(workbench,monkeypatch):
    w,app,_=workbench;w.smooth_enabled.setChecked(True);w.refresh_labels();settled(w,app)
    item=w.view.overlay_records['target'];previous=item.geometry_value
    started,release=delay_smoothing(monkeypatch)
    try:
        w.begin_reshape(auto=True)
        for x,y in OUT:w.add_reshape_point(x,y)
        w.finish_reshape();wait_until(app,lambda:w.task is None);wait_until(app,started.is_set)
        w.undo_context();assert shape(w.project['labels'][0]['geometry']).equals(box(20,20,30,30))
        assert w.view.overlay_records['target'] is item and item.geometry_value is previous
    finally:
        release.set();settled(w,app)
    assert not shape(item.geometry_value).equals(shape(w.project['labels'][0]['geometry']))


def test_confirming_reshaped_draft_keeps_smooth_outline_until_ready(workbench,monkeypatch):
    w,app,_=workbench;w.project['labels']=[];w.selected_id=None;w.selected_ids.clear()
    w.draft={'geometry':mapping(box(20,20,30,30)),'points':[],'pending':False}
    w.smooth_enabled.setChecked(True);w.refresh_labels();settled(w,app)
    previous=w.view.overlay_records['__draft'].geometry_value;started,release=delay_smoothing(monkeypatch)
    try:
        w.begin_reshape(auto=True)
        for x,y in OUT:w.add_reshape_point(x,y)
        w.finish_reshape();wait_until(app,lambda:w.task is None);wait_until(app,started.is_set)
        w.confirm();assert not w.draft and len(w.project['labels'])==1
        item=w.view.overlay_records[w.project['labels'][0]['id']]
        assert item.geometry_value is previous
    finally:
        release.set();settled(w,app)
    assert not shape(item.geometry_value).equals(shape(w.project['labels'][0]['geometry']))


def test_large_label_index_rebuild_keeps_smooth_outline(workbench,monkeypatch):
    from geoforma.controllers import label_list
    w,app,_=workbench;template=w.project['labels'][0]
    for i in range(33):
        x=40+(i%9)*6;y=40+(i//9)*6
        w.project['labels'].append(dict(template,id=f'extra-{i}',geometry=mapping(box(x,y,x+3,y+3))))
    w.smooth_enabled.setChecked(True);w.refresh_labels();wait_until(app,lambda:w.label_index_task is None);settled(w,app)
    item=w.view.overlay_records['target'];previous=item.geometry_value
    original=label_list.LabelIndex;started=threading.Event();release=threading.Event()
    def delayed_index(labels,task=None):
        started.set()
        while not release.wait(.005):
            if task:task.check()
        return original(labels,task=task)
    monkeypatch.setattr(label_list,'LabelIndex',delayed_index)
    try:
        w.begin_reshape(auto=True)
        for x,y in OUT:w.add_reshape_point(x,y)
        w.finish_reshape();wait_until(app,lambda:w.task is None);wait_until(app,started.is_set)
        assert w.view.overlay_records['target'] is item and item.geometry_value is previous
    finally:
        release.set();wait_until(app,lambda:w.label_index_task is None);settled(w,app)
    assert item.geometry_value is not w.project['labels'][0]['geometry']
    assert not shape(item.geometry_value).equals(shape(w.project['labels'][0]['geometry']))


def test_multiple_reshaped_labels_keep_smooth_outlines_together(workbench,monkeypatch):
    w,app,_=workbench
    w.project['labels'].append(dict(w.project['labels'][0],id='other',geometry=mapping(box(40,20,50,30))))
    w.smooth_enabled.setChecked(True);w.refresh_labels();settled(w,app)
    items={key:w.view.overlay_records[key] for key in ('target','other')}
    previous={key:item.geometry_value for key,item in items.items()};started,release=delay_smoothing(monkeypatch)
    try:
        w.begin_reshape(auto=True)
        for x,y in [[18,25],[52,25]]:w.add_reshape_point(x,y)
        w.finish_reshape();wait_until(app,lambda:w.task is None);wait_until(app,started.is_set)
        assert all(w.view.overlay_records[key] is item and item.geometry_value is previous[key] for key,item in items.items())
    finally:
        release.set();settled(w,app)
    for label in w.project['labels']:
        assert items[label['id']].geometry_value is not label['geometry']


def test_disconnected_parts_wait_for_smooth_results_without_raw_flash(workbench,monkeypatch):
    w,app,_=workbench;w.single_polygon.setChecked(False);w.smooth_enabled.setChecked(True);w.refresh_labels();settled(w,app)
    item=w.view.overlay_records['target'];previous=item.geometry_value
    started,release=delay_smoothing(monkeypatch)
    try:
        w.begin_reshape();session=w.reshape_session
        session['preview']={'geometry':mapping(MultiPolygon([box(20,20,24,30),box(26,20,30,30)])),
                            'stroke':OUT,'alternate':False,'window':[20,20,10,10],'added_pixels':0,'removed_pixels':20}
        w.commit_reshape();assert len(w.project['labels'])==2
        assert w.view.overlay_records['target'] is item and item.geometry_value is previous
        assert set(w.view.overlay_records)=={'target'}
        wait_until(app,started.is_set)
    finally:
        release.set();settled(w,app)
    assert set(w.view.overlay_records)=={label['id'] for label in w.project['labels']}
    assert all(w.view.overlay_records[label['id']].geometry_value is not label['geometry'] for label in w.project['labels'])
