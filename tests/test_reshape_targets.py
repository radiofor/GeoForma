"""Draft and click-to-pick reshape transactions, using a real local raster."""
import copy
import time
from PySide6.QtCore import Qt, QPointF
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QToolBar
import pytest
from shapely.geometry import shape
from test_reshape import workbench, raster_image, G, OUT


def preview(w, app):
    w.reshape_session['stroke']=copy.deepcopy(OUT)
    w.finish_reshape()
    deadline=time.monotonic()+5
    while w.task and time.monotonic()<deadline:
        app.processEvents();QTest.qWait(2)
    assert w.reshape_session is None and not w.view.reshape_items and not w.view.reshape_points
    assert w.draft['editing_state']=='manual'


def draft_target(w):
    w.project['labels']=[];w.selected_id=None;w.selected_ids.clear()
    w.draft={'geometry':copy.deepcopy(G),'points':[[25,25,1]],'pending':False,'window':[0,0,100,100]}
    w.refresh_labels()


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


def test_unsaved_draft_reshape_cancel_commit_undo_redo_and_confirm(workbench):
    w,app,_=workbench;draft_target(w);original=copy.deepcopy(w.draft)
    w.begin_reshape();w.add_reshape_point(22,28);w.cancel_reshape()
    assert w.draft==original and not w.project['labels']
    w.begin_reshape();preview(w,app)
    assert shape(w.view.overlay_records['__draft'].geometry_value).area==124
    assert not w.project['labels'] and shape(w.draft['geometry']).area==124
    assert w.model_prompts_locked() and len(w.draft['manual_edits'])==1
    calls=[];w.service.predict=lambda *a:calls.append(a)
    w.add_point(25,25,0);assert w.draft['points']==original['points'] and not calls
    w.undo_context();assert w.draft==original and not w.model_prompts_locked()
    w.redo_context();assert w.model_prompts_locked() and shape(w.draft['geometry']).area==124
    w.confirm()
    assert len(w.project['labels'])==1
    assert w.project['labels'][0]['editing_state']=='manual'
    assert len(w.project['labels'][0]['manual_edits'])==1


def test_unsaved_manual_history_survives_project_reopen(workbench):
    w,app,tmp=workbench;draft_target(w);w.begin_reshape();preview(w,app)
    w.project_path=tmp/'draft.gfm';w.save();w.open_project(w.project_path)
    assert w.draft['editing_state']=='manual' and not w.project['labels']
    w.undo_context();assert shape(w.draft['geometry']).equals(shape(G)) and not w.model_prompts_locked()
    w.redo_context();assert shape(w.draft['geometry']).area==124 and w.model_prompts_locked()


def test_reshaping_existing_draft_waits_for_label_confirmation(workbench):
    w,app,_=workbench;original=copy.deepcopy(w.project['labels'][0])
    w.edit_selected(locate=False);w.begin_reshape();preview(w,app)
    assert w.project['labels'][0]==original and w.draft['editing_state']=='manual'
    w.confirm()
    assert len(w.project['labels'])==1 and w.project['labels'][0]['id']=='target'
    assert shape(w.project['labels'][0]['geometry']).area==124
    assert w.project['labels'][0]['editing_state']=='manual' and not w.model_prompts_locked()
    w.undo_context();w.select_label('target')
    assert w.project['labels'][0]==original and not w.model_prompts_locked()


@pytest.mark.parametrize('method',['button','right_click'])
def test_finish_controls_apply_and_leave_tool_without_saving(workbench,method):
    w,app,_=workbench;original=copy.deepcopy(w.project['labels'])
    w.show();app.processEvents();w.begin_reshape()
    w.reshape_session['stroke']=copy.deepcopy(OUT);w.view.set_reshape_stroke(OUT);w.update_controls()
    if method=='button':w.reshape_preview_button.click()
    else:QTest.mouseClick(w.view.viewport(),Qt.MouseButton.RightButton)
    deadline=time.monotonic()+5
    while w.task and time.monotonic()<deadline:app.processEvents();QTest.qWait(2)
    assert w.reshape_session is None and not w.view.reshape_items and w.view.mode=='reshape'
    assert not w.reshape_group.isVisible() and w.editor_group.isVisible()
    assert w.project['labels']==original and shape(w.draft['geometry']).area==124
    assert w.confirm_button.isEnabled()
    w.undo_context();assert shape(w.draft['geometry']).equals(shape(G)) and not w.model_prompts_locked()


def test_unsaved_pending_stroke_survives_project_reopen(workbench):
    w,app,tmp=workbench;draft_target(w);w.begin_reshape()
    w.add_reshape_point(22,28);w.add_reshape_point(22,34)
    w.project_path=tmp/'pending.gfm'
    w.capture_workspace()
    from geoforma.storage import save_project
    save_project(w.project,w.project_path)
    w.cancel_reshape();w.open_project(w.project_path)
    assert w.reshape_session['target']=='draft' and len(w.reshape_session['stroke'])==2
    assert shape(w.draft['geometry']).equals(shape(G)) and not w.project['labels']


