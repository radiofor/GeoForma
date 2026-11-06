"""Fill is an interruptible view of unchanged, editable source geometry."""
import copy
import threading,time
from PySide6.QtCore import QEvent
from PySide6.QtTest import QTest
from shapely.geometry import box,mapping,shape
from test_reshape import workbench,raster_image
from test_smoothing import settled


def test_fill_switch_is_reversible_and_crossfades_in_both_directions(workbench):
    w,app,_=workbench
    w.fill_holes.setChecked(False);w.smooth_enabled.setChecked(False)
    original=box(20,20,40,40).difference(box(25,25,35,35))
    w.project['labels'][0]['geometry']=mapping(original);before=copy.deepcopy(w.project['labels'])
    w.refresh_labels();settled(w,app)
    item=w.view.overlay_records['target'];assert len(shape(item.geometry_value).interiors)==1
    w.fill_holes.setChecked(True);settled(w,app)
    transition=w.view.label_transition;transition.animation.pause();transition.advance(.5)
    assert not shape(item.geometry_value).interiors and item.opacity()==.5 and transition.ghosts
    assert w.project['labels']==before
    w.fill_holes.setChecked(False);app.processEvents()
    transition.animation.pause();transition.advance(.5)
    assert len(shape(item.geometry_value).interiors)==1 and item.opacity()==.5 and transition.ghosts
    assert w.project['labels']==before
    transition.eventFilter(w.view.viewport(),QEvent(QEvent.Type.KeyPress))
    assert item.opacity()==1 and not transition.ghosts


def test_rapid_fill_toggles_publish_only_latest_result(workbench):
    w,app,_=workbench
    w.fill_holes.setChecked(False);w.smooth_enabled.setChecked(True)
    original=box(20,20,40,40).difference(box(25,25,35,35))
    w.project['labels'][0]['geometry']=mapping(original);before=copy.deepcopy(w.project['labels'])
    w.refresh_labels();settled(w,app)
    for value in (True,False,True,False):w.fill_holes.setChecked(value)
    settled(w,app)
    assert len(shape(w.view.overlay_records['target'].geometry_value).interiors)==1
    assert w.project['labels']==before


def test_disabling_fill_while_old_work_runs_restores_source(workbench,monkeypatch):
    from geoforma import label_presentation
    w,app,_=workbench;w.fill_holes.setChecked(False);w.smooth_enabled.setChecked(False)
    original=box(20,20,40,40).difference(box(25,25,35,35))
    geometry=mapping(original);w.project['labels'][0]['geometry']=geometry;w.refresh_labels()
    started=threading.Event();release=threading.Event();real=label_presentation.presentation_batch
    def delayed(labels,fill,config,image,task,cache):
        started.set()
        while not release.wait(.005):task.check()
        return real(labels,fill,config,image,task,cache)
    monkeypatch.setattr(label_presentation,'presentation_batch',delayed)
    try:
        w.fill_holes.setChecked(True);deadline=time.monotonic()+5
        while not started.is_set() and time.monotonic()<deadline:app.processEvents();QTest.qWait(2)
        assert started.is_set()
        w.fill_holes.setChecked(False)
        assert w.view.overlay_records['target'].geometry_value is geometry
        release.set();settled(w,app)
        assert w.view.overlay_records['target'].geometry_value is geometry
    finally:release.set()


def test_switching_image_clears_label_transition(workbench):
    w,app,_=workbench;w.fill_holes.setChecked(False);w.smooth_enabled.setChecked(False)
    w.project['labels'][0]['geometry']=mapping(box(20,20,40,40).difference(box(25,25,35,35)))
    w.refresh_labels();w.fill_holes.setChecked(True);settled(w,app)
    transition=w.view.label_transition;transition.animation.pause();transition.advance(.5)
    assert transition.ghosts
    w.view.switch_image(100,100)
    assert not transition.ghosts and not transition.new_items
    w.view.set_image(100,100);app.processEvents()


def test_pending_toggle_keeps_current_blend_until_new_result(workbench,monkeypatch):
    from geoforma import label_presentation
    w,app,_=workbench;w.fill_holes.setChecked(False);w.smooth_enabled.setChecked(True)
    w.project['labels'][0]['geometry']=mapping(box(20,20,40,40).difference(box(25,25,35,35)))
    w.refresh_labels();settled(w,app);w.fill_holes.setChecked(True);settled(w,app)
    transition=w.view.label_transition;transition.animation.pause();transition.advance(.5)
    item=w.view.overlay_records['target'];old_ghosts=[ghost for _,ghost,_ in transition.ghosts]
    assert old_ghosts and item.opacity()==.5
    w.smoother.cache.clear()
    started=threading.Event();release=threading.Event();real=label_presentation.presentation_batch
    def delayed(labels,fill,config,image,task,cache):
        started.set()
        while not release.wait(.005):task.check()
        return real(labels,fill,config,image,task,cache)
    monkeypatch.setattr(label_presentation,'presentation_batch',delayed)
    try:
        w.fill_holes.setChecked(False);deadline=time.monotonic()+5
        while not started.is_set() and time.monotonic()<deadline:app.processEvents();QTest.qWait(2)
        assert started.is_set() and [ghost for _,ghost,_ in transition.ghosts]==old_ghosts
        assert item.opacity()==.5
        release.set();settled(w,app)
        assert len(shape(item.geometry_value).interiors)==1 and transition.ghosts
    finally:release.set()


def test_pending_toggle_is_discarded_on_context_change_and_error(workbench,monkeypatch):
    from geoforma import label_presentation
    w,app,_=workbench;w.fill_holes.setChecked(False);w.smooth_enabled.setChecked(False)
    w.project['labels'][0]['geometry']=mapping(box(20,20,40,40).difference(box(25,25,35,35)))
    w.refresh_labels();started=threading.Event();release=threading.Event();real=label_presentation.presentation_batch
    def delayed(labels,fill,config,image,task,cache):
        started.set()
        while not release.wait(.005):task.check()
        return real(labels,fill,config,image,task,cache)
    monkeypatch.setattr(label_presentation,'presentation_batch',delayed)
    try:
        w.fill_holes.setChecked(True);deadline=time.monotonic()+5
        while not started.is_set() and time.monotonic()<deadline:app.processEvents();QTest.qWait(2)
        assert started.is_set() and w._presentation_transition_pending
        w.project_epoch+=1;w.redraw()
        assert not w._presentation_transition_pending
        release.set();settled(w,app)
        assert not w._presentation_transition_pending
        w._presentation_transition_pending=True;w.smoothing_error('模拟错误')
        assert not w._presentation_transition_pending
    finally:release.set()
