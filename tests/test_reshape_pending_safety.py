"""A retained old outline must never be edited as the new geometry."""
import pytest
from shapely.geometry import box, mapping
from test_reshape import OUT, workbench, raster_image
from test_smoothing import settled
from test_smoothing_reshape_transition import delay_smoothing, wait_until


def test_retained_outline_temporarily_disables_all_reshape_entry_points(workbench, monkeypatch):
    w,app,_=workbench
    w.smooth_enabled.setChecked(True);w.refresh_labels();settled(w,app)
    started,release=delay_smoothing(monkeypatch)
    try:
        w.begin_reshape(auto=True)
        for x,y in OUT:w.add_reshape_point(x,y)
        w.finish_reshape();wait_until(app,lambda:w.task is None);wait_until(app,started.is_set)
        assert w._reshape_smoothing_hold
        assert not w.mode_actions['reshape'].isEnabled()
        assert not w.view.reshape_enabled
        before=w.project['labels'][0]['geometry']
        w.begin_reshape(auto=True);w.begin_reshape();w.add_reshape_point(25,25)
        assert w.reshape_session is None and w.project['labels'][0]['geometry'] is before
        w.cancel_reshape()
        assert w.reshape_session is None
    finally:
        release.set();settled(w,app)
    assert not w._reshape_smoothing_hold
    assert w.mode_actions['reshape'].isEnabled()
    w.begin_reshape(auto=True)
    assert w.reshape_session is not None


def test_leaving_context_clears_retained_outline_gate(workbench):
    w,app,_=workbench
    w._reshape_smoothing_hold=(('obsolete',),(),{}, {})
    w.redraw();w.update_controls()
    assert not w._reshape_smoothing_hold
    assert w.mode_actions['reshape'].isEnabled()


def test_disabling_smoothing_cancels_pending_hold_and_reenables_reshape(workbench, monkeypatch):
    w,app,_=workbench
    w.smooth_enabled.setChecked(True);w.refresh_labels();settled(w,app)
    started,release=delay_smoothing(monkeypatch)
    try:
        w.begin_reshape(auto=True)
        for x,y in OUT:w.add_reshape_point(x,y)
        w.finish_reshape();wait_until(app,lambda:w.task is None);wait_until(app,started.is_set)
        assert not w.mode_actions['reshape'].isEnabled()
        w.smooth_enabled.setChecked(False);app.processEvents()
        assert not w._reshape_smoothing_hold
        assert w.mode_actions['reshape'].isEnabled()
        assert w.view.reshape_enabled
    finally:
        release.set();settled(w,app)


@pytest.mark.parametrize('option',['fill','strength','enable'])
def test_pending_option_change_disables_reshape_until_visible_outline_ready(workbench,monkeypatch,option):
    w,app,_=workbench
    w.project['labels'][0]['geometry']=mapping(box(20,20,30,30).difference(box(23,23,25,25)))
    w.fill_holes.setChecked(False);w.smooth_enabled.setChecked(option!='enable')
    w.refresh_labels();settled(w,app)
    old=w.view.overlay_records['target'].geometry_value
    started,release=delay_smoothing(monkeypatch)
    try:
        if option=='fill':w.fill_holes.setChecked(True)
        elif option=='strength':w.smooth_value.setValue(2)
        else:w.smooth_enabled.setChecked(True)
        wait_until(app,started.is_set)
        assert w.view.overlay_records['target'].geometry_value is old
        assert not w.mode_actions['reshape'].isEnabled()
        w.begin_reshape(auto=True);w.add_reshape_point(25,25)
        assert w.reshape_session is None
    finally:
        release.set();settled(w,app)
    assert w.mode_actions['reshape'].isEnabled()
    w.begin_reshape(auto=True);assert w.reshape_session is not None


def test_reshape_option_gate_ignores_other_image_context(workbench):
    from geoforma.tool_state import reshape_presentation_pending
    w,app,_=workbench
    w._presentation_transition_pending=True;w._presentation_ready=False
    w._presentation_transition_context=('another image',)
    assert not reshape_presentation_pending(w)


def test_failed_option_change_blocks_stale_outline_until_setting_recovers(workbench,monkeypatch):
    from geoforma import smoothing
    w,app,_=workbench;w.fill_holes.setChecked(False)
    w.smooth_enabled.setChecked(True);w.refresh_labels();settled(w,app)
    def fail(*args,**kwargs):raise ValueError('synthetic failure')
    monkeypatch.setattr(smoothing,'smooth_batch',fail)
    w.smooth_value.setValue(2)
    wait_until(app,lambda:getattr(w,'_presentation_failed_context',None)==w.annotation_context())
    assert not w.mode_actions['reshape'].isEnabled()
    w.begin_reshape(auto=True);assert w.reshape_session is None
    w.smooth_enabled.setChecked(False);app.processEvents()
    assert w._presentation_failed_context is None
    assert w.mode_actions['reshape'].isEnabled()


def test_failed_option_change_does_not_block_another_context(workbench):
    from geoforma.tool_state import reshape_presentation_pending
    w,app,_=workbench
    w._presentation_failed_context=('another image',)
    assert not reshape_presentation_pending(w)
