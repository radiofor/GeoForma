"""Manual polygons work without a model and use the normal label lifecycle."""
import copy
import pytest
from PySide6.QtCore import Qt,QPointF
from PySide6.QtTest import QTest
from shapely.geometry import shape
from test_reshape import workbench,raster_image


def click_vertex(w,x,y):
    QTest.mouseClick(w.view.viewport(),Qt.MouseButton.LeftButton,pos=w.view.mapFromScene(QPointF(x,y)))


@pytest.mark.parametrize('finish',['right','double'])
def test_draw_save_and_undo_without_model_preparation(workbench,finish):
    w,app,_=workbench;w.show();app.processEvents();w.image['ready']=False;w.update_controls()
    actions=w.image_toolbar.actions()
    assert actions.index(w.mode_actions['draw_polygon'])+1==actions.index(w.mode_actions['reshape'])
    assert w.mode_actions['draw_polygon'].isEnabled()
    w.mode_actions['draw_polygon'].trigger();assert w.view.mode=='draw_polygon'
    click_vertex(w,40,40);click_vertex(w,65,40);click_vertex(w,65,65)
    assert len(w.draft['manual_vertices'])==3 and not w.confirm_button.isEnabled()
    QTest.keyClick(w.view.viewport(),Qt.Key.Key_Backspace)
    assert len(w.draft['manual_vertices'])==2
    click_vertex(w,65,65)
    if finish=='right':
        click_vertex(w,40,65);QTest.mouseClick(w.view.viewport(),Qt.MouseButton.RightButton)
    else:QTest.mouseDClick(w.view.viewport(),Qt.MouseButton.LeftButton,pos=w.view.mapFromScene(QPointF(40,65)))
    assert w.confirm_button.isEnabled() and w.draft['editing_state']=='manual'
    assert shape(w.draft['geometry']).is_valid and shape(w.draft['geometry']).area>500
    w.view.setFocus();QTest.keyClick(w.view.viewport(),Qt.Key.Key_Return);app.processEvents()
    label=next(label for label in w.project['labels'] if label.get('source')=='manual_draw')
    assert label['manual_edits'][0]['tool']=='draw_polygon' and label['editing_state']=='manual'
    assert 'backend' not in label['model'] and label['class_id']==w.classes.currentData()
    w.undo_context();assert all(label.get('source')!='manual_draw' for label in w.project['labels'])
    w.redo_context();assert any(label.get('source')=='manual_draw' for label in w.project['labels'])
    from geoforma.project_validation import validate_project
    validate_project(w.project)


def test_invalid_polygon_can_be_corrected_or_cancelled(workbench):
    w,app,_=workbench;w.show();app.processEvents();w.set_tool('draw_polygon')
    for p in ((40,40),(60,60),(40,60),(60,40)):click_vertex(w,*p)
    QTest.mouseClick(w.view.viewport(),Qt.MouseButton.RightButton)
    assert len(w.draft['manual_vertices'])==4 and not w.confirm_button.isEnabled()
    assert '无效' in w.statusBar().currentMessage()
    QTest.keyClick(w.view.viewport(),Qt.Key.Key_Escape)
    assert not w.draft and not w.view.reshape_items


def test_preview_is_filled_and_escape_cancels_completed_draft(workbench):
    w,app,_=workbench;w.show();app.processEvents();w.set_tool('draw_polygon')
    for p in ((40,40),(65,40),(65,65)):click_vertex(w,*p)
    assert w.view.polygon_fill is not None
    assert w.view.polygon_fill.path().contains(QPointF(60,45))
    QTest.mouseClick(w.view.viewport(),Qt.MouseButton.RightButton)
    assert w.draft.get('geometry') and w.confirm_button.isEnabled()
    QTest.keyClick(w.view.viewport(),Qt.Key.Key_Escape)
    assert not w.draft and not w.confirm_button.isEnabled()
    assert not any(label.get('source')=='manual_draw' for label in w.project['labels'])


def test_unfinished_drawing_survives_switching_images(workbench,monkeypatch):
    w,app,_=workbench;w.show();app.processEvents();w.set_tool('draw_polygon')
    click_vertex(w,40,40);click_vertex(w,65,40)
    vertices=copy.deepcopy(w.draft['manual_vertices'])
    other=copy.deepcopy(w.image);other.update(id='another',name='another.tif')
    w.project['images'].append(other);monkeypatch.setattr(w,'request_render',lambda *args:None)
    w._activate_image(1);assert not w.draft and not w.view.reshape_items
    w._activate_image(0);assert w.draft['manual_vertices']==vertices
    assert w.view.reshape_points==vertices and w.view.reshape_items
    w.cancel_manual_polygon()


def test_unfinished_drawing_is_preserved_in_the_project(workbench):
    w,app,tmp=workbench;w.show();app.processEvents();w.set_tool('draw_polygon')
    click_vertex(w,40,40);click_vertex(w,65,40)
    vertices=copy.deepcopy(w.draft['manual_vertices']);w.capture_workspace()
    from geoforma.storage import save_project,load_project
    path=tmp/'manual.gfm';save_project(w.project,path)
    restored=load_project(path)
    assert restored['workspace']['tool']=='draw_polygon'
    assert restored['workspace']['draft']['manual_vertices']==vertices
    assert restored['images'][0]['mode_sessions']['individual']['draft']['manual_vertices']==vertices
    w.cancel_manual_polygon()
