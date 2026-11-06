"""Draft and click-to-pick reshape transactions, using a real local raster."""
import copy
import time
from PySide6.QtCore import Qt, QPointF
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QToolBar
from shapely.geometry import shape
from test_reshape import workbench, raster_image, G, OUT






def test_toolbar_draws_immediately_without_selecting_a_label(workbench):
    w,app,_=workbench
    w.show();app.processEvents();w.view.fit_image();w.render_timer.stop()
    assert any(w.mode_actions['reshape'] in bar.actions() for bar in w.findChildren(QToolBar))
    w.selected_id=None;w.selected_ids.clear();w.refresh_labels()
    w.reshape_button.click()
    assert w.reshape_session['target']=='auto' and not w.view.reshape_picking
    QTest.mouseClick(w.view.viewport(),Qt.MouseButton.LeftButton,pos=w.view.mapFromScene(QPointF(25,25)))
    assert len(w.reshape_session['stroke'])==1 and not w.selected_ids
    assert w.mode_actions['reshape'].isChecked()
    w.cancel_reshape()
    assert w.mode_actions['reshape'].isChecked() and w.view.reshape_picking


def test_reshape_keyboard_alternate_and_cancel_without_changing_panel(workbench):
    w,app,_=workbench;w.show();app.processEvents();w.begin_reshape(auto=True)
    assert w.mode_settings.currentWidget() is w.prompt_group
    w.view.setFocus();app.processEvents()
    QTest.keyClick(w.view.viewport(),Qt.Key.Key_R);app.processEvents()
    assert w.reshape_session['alternate']
    QTest.keyClick(w.view.viewport(),Qt.Key.Key_Escape);app.processEvents()
    assert w.reshape_session is None and w.mode_settings.currentWidget() is w.prompt_group








def test_finish_controls_save_and_leave_tool(workbench):
    w,app,_=workbench;original=copy.deepcopy(w.project['labels'])
    w.show();app.processEvents();w.begin_reshape()
    w.reshape_session['stroke']=copy.deepcopy(OUT);w.view.set_reshape_stroke(OUT);w.update_controls()
    QTest.mouseClick(w.view.viewport(),Qt.MouseButton.RightButton)
    deadline=time.monotonic()+5
    while w.task and time.monotonic()<deadline:app.processEvents();QTest.qWait(2)
    assert w.reshape_session is None and not w.view.reshape_items and w.view.mode=='reshape'
    assert w.mode_settings.currentWidget() is w.prompt_group and w.editor_group.isVisible()
    assert w.project['labels']!=original and not w.draft
    assert shape(w.project['labels'][0]['geometry']).area==124
    assert not w.confirm_button.isEnabled()
    w.undo_context();assert w.project['labels']==original and not w.model_prompts_locked()




