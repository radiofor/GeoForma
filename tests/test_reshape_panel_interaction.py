"""A reshape stroke must not lock unrelated panels or disappear on option changes."""
from test_reshape import workbench,raster_image,OUT
from test_smoothing import settled


def test_repeated_toolbar_click_keeps_tool_and_panels_consistent(workbench):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    w,app,_=workbench;w.show();app.processEvents()
    for _ in range(2):
        QTest.mouseClick(w.reshape_button,Qt.MouseButton.LeftButton);app.processEvents()
        assert w.mode_actions['reshape'].isChecked() and w.view.selected_mode=='reshape'
        assert w.reshape_session is not None and w.images.isEnabled() and w.editor_group.isEnabled()


def test_reshape_tool_and_stroke_leave_panels_and_tool_switching_available(workbench):
    w,app,_=workbench
    w.begin_reshape(auto=True);app.processEvents()
    assert w.images.isEnabled() and w.editor_group.isEnabled() and w.classes_button.isEnabled()
    assert w.import_button.isEnabled() and w.import_reference_button.isEnabled()
    assert w.mode_actions['draw_polygon'].isEnabled()
    w.add_reshape_point(*OUT[0]);app.processEvents()
    assert w.images.isEnabled() and w.editor_group.isEnabled() and w.mode_actions['draw_polygon'].isEnabled()
    w.set_tool('draw_polygon')
    assert w.reshape_session is None and w.view.mode=='draw_polygon'


def test_option_changes_keep_stroke_and_wait_for_presentation(workbench,monkeypatch):
    from geoforma import tool_state
    w,app,_=workbench
    w.begin_reshape(auto=True)
    for point in OUT[:3]:w.add_reshape_point(*point)
    session=w.reshape_session;before=[list(p) for p in session['stroke']]
    w.single_polygon.setChecked(not w.single_polygon.isChecked())
    w.fill_holes.setChecked(not w.fill_holes.isChecked())
    w.smooth_enabled.setChecked(not w.smooth_enabled.isChecked())
    assert w.reshape_session is session and session['stroke']==before
    monkeypatch.setattr(tool_state,'reshape_presentation_pending',lambda _:True)
    w.add_reshape_point(1,1);w.finish_reshape()
    assert w.reshape_session is session and session['stroke']==before and not w.task
    monkeypatch.undo();settled(w,app)
    assert w.reshape_session is session and session['stroke']==before


def test_switching_image_discards_line_only_on_actual_activation(workbench):
    import copy
    w,app,_=workbench;other=copy.deepcopy(w.image);other['id']='other'
    w.project['images'].append(other);w.refresh_images();w.begin_reshape(auto=True)
    w.add_reshape_point(*OUT[0]);session=w.reshape_session
    current=w.image;w.change_image(-1)
    assert w.image is current and w.reshape_session is session
    w._activate_image(1)
    assert w.image is other and w.reshape_session is None


def test_empty_reshape_does_not_block_saved_undo_or_delete(workbench):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    w,app,_=workbench
    original=w.project['labels'][0];w.select_label(original['id']);w.delete_selected()
    assert not w.project['labels']
    w.undo_label();w.select_label(original['id']);w.begin_reshape(auto=True)
    assert w.delete_action.isEnabled() and not w.new_target_button.isEnabled()
    w.delete_selection();assert not w.project['labels'] and w.reshape_session is None
    w.undo_label();w.select_label(original['id']);w.begin_reshape(auto=True)
    w.view.setFocus();QTest.keyClick(w.view,Qt.Key.Key_Escape);app.processEvents()
    assert w.reshape_session is None


def test_ctrl_z_prefers_stroke_then_saved_history(workbench):
    w,app,_=workbench
    label=w.project['labels'][0];w.select_label(label['id']);w.delete_selected();w.undo_label()
    w.begin_reshape(auto=True);w.add_reshape_point(*OUT[0])
    w.undo_context();assert w.reshape_session is not None and not w.reshape_session['stroke']
    w.redo_context();assert w.reshape_session['stroke']


def test_empty_session_does_not_swallow_composite_undo_redo(workbench):
    import copy
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from shapely.geometry import box,mapping,shape
    w,app,_=workbench;original=copy.deepcopy(w.project['labels'][0]);changed=copy.deepcopy(original)
    changed['geometry']=mapping(box(20,20,35,35));w.project['labels']=[changed];w.refresh_labels()
    w.prompt_undo=[{'_draft':{},'_label_entries':[(original['id'],original,0)]}]
    w.show();w.activateWindow();w.begin_reshape(auto=True);assert w.reshape_session
    assert w.undo_prompt_action.isEnabled()
    w.view.setFocus();app.processEvents();QTest.keyClick(w.view,Qt.Key.Key_Z,Qt.KeyboardModifier.ControlModifier);app.processEvents()
    assert w.reshape_session is None
    assert shape(w.project['labels'][0]['geometry']).equals(shape(original['geometry']))
    w.begin_reshape(auto=True);assert w.redo_prompt_action.isEnabled()
    w.view.setFocus();app.processEvents();QTest.keyClick(w.view,Qt.Key.Key_Z,Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.ShiftModifier);app.processEvents()
    assert w.reshape_session is None
    assert shape(w.project['labels'][0]['geometry']).equals(shape(changed['geometry']))


def test_failed_image_preload_preserves_reshape_line(workbench):
    import copy,time
    import numpy as np
    w,app,_=workbench;other=copy.deepcopy(w.image);other['id']='other'
    other['display_recipe']={'bands':[1,2,3]};w.project['images'].append(other);w.refresh_images()
    w.view.show_raster(np.zeros((3,3,3),np.uint8),np.ones((3,3),bool),(0,0,w.image['width'],w.image['height']),True)
    def fail(*args):raise ValueError('test failure')
    w.raster_renderer.reader=fail
    w.begin_reshape(auto=True);w.add_reshape_point(*OUT[0]);session=w.reshape_session
    w.change_image(1);deadline=time.monotonic()+5
    while getattr(w,'_image_switch_task',None) is not None:
        app.processEvents();time.sleep(.002);assert time.monotonic()<deadline
    assert w.image is not other and w.reshape_session is session and session['stroke']==[OUT[0]]


def test_escape_works_outside_view_and_dropdown_consumes_its_own_escape(workbench):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    w,app,_=workbench;w.show();app.processEvents()
    w.begin_reshape(auto=True);w.add_reshape_point(*OUT[0]);session=w.reshape_session
    w.classes.setFocus();w.classes.showPopup();app.processEvents()
    popup=w.classes.view();assert popup.isVisible()
    QTest.keyClick(popup,Qt.Key.Key_Escape);app.processEvents()
    assert not popup.isVisible() and w.reshape_session is session
    w.activateWindow();w.labels_table.setFocus();app.processEvents()
    QTest.keyClick(w.labels_table,Qt.Key.Key_Escape);app.processEvents()
    assert w.reshape_session is None


def test_delayed_option_update_preserves_line_and_finishes_with_new_setting(workbench,monkeypatch):
    from test_smoothing_reshape_transition import delay_smoothing,wait_until
    from test_reshape_auto import wait
    w,app,_=workbench;w.fill_holes.setChecked(False);w.smooth_enabled.setChecked(False)
    w.begin_reshape(auto=True)
    for point in OUT:w.add_reshape_point(*point)
    session=w.reshape_session;before=[list(p) for p in session['stroke']]
    started,release=delay_smoothing(monkeypatch)
    try:
        w.smooth_enabled.setChecked(True);wait_until(app,started.is_set)
        w.finish_reshape();assert w.reshape_session is session and session['stroke']==before and not w.task
    finally:release.set()
    settled(w,app);w.finish_reshape();wait(w,app)
    assert w.reshape_session is None and w.smooth_enabled.isChecked()


def test_failed_option_update_keeps_line_until_option_restores(workbench,monkeypatch):
    from geoforma import smoothing
    from test_smoothing_reshape_transition import wait_until
    from test_reshape_auto import wait
    w,app,_=workbench;w.fill_holes.setChecked(False);w.smooth_enabled.setChecked(False)
    w.begin_reshape(auto=True)
    for point in OUT:w.add_reshape_point(*point)
    session=w.reshape_session;before=[list(p) for p in session['stroke']]
    def fail(*args,**kwargs):raise ValueError('synthetic failure')
    monkeypatch.setattr(smoothing,'smooth_batch',fail)
    w.smooth_enabled.setChecked(True)
    wait_until(app,lambda:getattr(w,'_presentation_failed_context',None)==w.annotation_context())
    w.finish_reshape();assert w.reshape_session is session and session['stroke']==before
    w.smooth_enabled.setChecked(False);app.processEvents()
    w.finish_reshape();wait(w,app);assert w.reshape_session is None
