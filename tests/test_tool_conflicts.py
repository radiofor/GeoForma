import copy,time
import pytest
from test_reshape import workbench,raster_image,OUT


def test_pan_suspends_stroke_and_reshape_resumes_without_losing_points(workbench):
    w,app,_=workbench;w.begin_reshape();w.add_reshape_point(22,28)
    session=w.reshape_session;stroke=copy.deepcopy(session['stroke'])
    for mode in ('pan','reshape','pan','reshape'):
        assert w.mode_actions[mode].isEnabled()
        w.mode_actions[mode].trigger()
        assert w.view.mode==mode and w.mode_actions[mode].isChecked()
        assert w.reshape_session is session and session['stroke']==stroke
    assert w.fit_action.isEnabled() and w.native_zoom_action.isEnabled() and w.raw_view_action.isEnabled()


@pytest.mark.parametrize('tool',['positive','negative','box','select_points','select'])
def test_explicit_edit_tool_switch_cancels_only_construction_line(workbench,tool):
    w,app,_=workbench;before=copy.deepcopy(w.project['labels'])
    w.begin_reshape();w.add_reshape_point(22,28)
    assert w.mode_actions[tool].isEnabled()
    w.mode_actions[tool].trigger()
    assert w.view.mode==tool and w.mode_actions[tool].isChecked()
    assert w.reshape_session is None and not w.view.reshape_points
    assert w.project['labels']==before
    assert w.images.isEnabled() and w.import_action.isEnabled()


def test_target_controls_and_navigation_remain_available_during_reshape(workbench):
    w,app,_=workbench;w.begin_reshape()
    for control in (w.images,w.model_button,w.import_button,w.import_action):
        assert control.isEnabled()
    assert not w.confirm_button.isEnabled()
    assert w.project_actions['save'].isEnabled() and not w.project_actions['recover'].isEnabled()
    assert w.labels_table.isEnabled() and w.fit_action.isEnabled()
    w.add_reshape_point(*OUT[0]);assert w.reshape_session['stroke']
    w.set_tool('select');assert w.reshape_session is None and w.view.mode=='select'


def test_reshaped_saved_label_allows_switching_to_prompt_tools(workbench):
    w,app,_=workbench;w.begin_reshape();w.reshape_session['stroke']=copy.deepcopy(OUT);w.finish_reshape()
    deadline=time.monotonic()+8
    while w.task and time.monotonic()<deadline:app.processEvents();time.sleep(.002)
    assert w.task is None and w.reshape_session is None
    w.begin_reshape(auto=True)
    assert w.mode_actions['positive'].isEnabled()
    w.set_tool('positive')
    assert w.view.mode=='positive' and w.reshape_session is None


def test_busy_calculation_allows_navigation_but_rejects_editing(workbench):
    from geoforma.tool_state import available_tools
    w,app,_=workbench;w.begin_reshape()
    w.task=object();w.task_kind='reshape'
    try:
        tools=available_tools(w)
        assert tools['pan'] and not any(value for mode,value in tools.items() if mode!='pan')
        w.set_tool('select')
        assert w.view.mode=='reshape' and w.mode_actions['reshape'].isChecked()
    finally:w.task=None;w.task_kind=None
