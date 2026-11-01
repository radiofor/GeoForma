"""Direct strokes edit every crossed target and wait for one explicit save."""
import copy,time,json
import pytest
from PySide6.QtCore import Qt,QPointF
from PySide6.QtTest import QTest
from shapely.geometry import box,mapping,shape
from test_reshape import workbench,raster_image,OUT
from test_smoothing import settled


@pytest.fixture(autouse=True)
def fail_on_dialog(workbench,monkeypatch):
    def fail(message):raise AssertionError(message)
    monkeypatch.setattr(workbench[0],'error',fail)


def wait(w,app):
    deadline=time.monotonic()+8
    while w.task:
        app.processEvents();QTest.qWait(2);assert time.monotonic()<deadline
    settled(w,app)


def draw(w,app,points):
    w.show();app.processEvents();w.view.fit_image();w.reshape_button.click()
    for x,y in points:
        QTest.mouseClick(w.view.viewport(),Qt.MouseButton.LeftButton,pos=w.view.mapFromScene(QPointF(x,y)))
    QTest.mouseClick(w.view.viewport(),Qt.MouseButton.RightButton);wait(w,app)


@pytest.mark.parametrize('selected',[None,'target','other'])
def test_stroke_ignores_selection_and_stays_smooth_until_enter(workbench,selected):
    w,app,_=workbench
    w.project['labels'].append(dict(w.project['labels'][0],id='other',geometry=mapping(box(60,60,70,70))))
    w.selected_id=selected;w.selected_ids={selected} if selected else set();w.refresh_labels()
    before=copy.deepcopy(w.project['labels']);w.smooth_enabled.setChecked(True);settled(w,app)
    draw(w,app,OUT)
    assert w.project['labels']==before and w.draft['base_id']=='target'
    assert not shape(w.view.overlay_records['__draft'].geometry_value).equals(shape(w.draft['geometry']))
    QTest.keyClick(w.view.viewport(),Qt.Key.Key_Return);wait(w,app)
    assert not w.draft
    assert all(row.status=='已保存' for row in w.label_presenter.rows)
    assert next(l for l in w.project['labels'] if l['id']=='other')==before[1]
    assert not shape(w.view.overlay_records['target'].geometry_value).equals(shape(next(l for l in w.project['labels'] if l['id']=='target')['geometry']))


def two_labels(w):
    w.project['labels'].append(dict(w.project['labels'][0],id='other',class_id=2,geometry=mapping(box(40,20,50,30))))
    w.project['classes'].append({'id':2,'name':'第二类','value':2,'color':'#00ff00'})
    w.refresh_labels()


def test_multiple_crossed_labels_save_and_undo_as_one_transaction(workbench):
    w,app,tmp=workbench;two_labels(w);before=copy.deepcopy(w.project['labels'])
    draw(w,app,[[18,25],[52,25]])
    assert len(w.draft['reshape_batch'])==2 and w.project['labels']==before
    assert all(row.status=='未保存' for row in w.label_presenter.rows)
    assert shape(w.view.overlay_records['other'].geometry_value).area<100
    # Unsaved results survive reopening and remain a single confirmation.
    w.project_path=tmp/'batch.geoforma.json';w.save();w.open_project(w.project_path);wait(w,app)
    assert len(w.draft['reshape_batch'])==2
    QTest.keyClick(w.view.viewport(),Qt.Key.Key_Return);wait(w,app)
    assert not w.draft and len(w.label_undo)==1
    assert all(l['editing_state']=='manual' and shape(l['geometry']).area<100 for l in w.project['labels'])
    assert {l['class_id'] for l in w.project['labels']}=={1,2}
    assert all(row.status=='已保存' for row in w.label_presenter.rows)
    saved=copy.deepcopy(w.project['labels']);w.undo_label();assert json.loads(json.dumps(w.project['labels']))==json.loads(json.dumps(before))
    w.redo_label();assert w.project['labels']==saved


def test_invalid_target_keeps_the_entire_batch_unchanged(workbench):
    w,app,_=workbench;two_labels(w);before=copy.deepcopy(w.project['labels'])
    # The last target is entered only once, so no target is staged or saved.
    draw(w,app,[[18,25],[45,25]])
    assert w.reshape_session and w.reshape_session.get('error')
    assert w.project['labels']==before and not w.draft and not w.label_undo


def test_unbound_stroke_survives_reopen(workbench):
    w,app,tmp=workbench;w.begin_reshape(auto=True);w.add_reshape_point(18,25);w.add_reshape_point(52,25)
    w.project_path=tmp/'stroke.geoforma.json';w.save();w.cancel_reshape();w.open_project(w.project_path);wait(w,app)
    assert w.reshape_session['target']=='auto' and w.reshape_session['stroke']==[[18,25],[52,25]]


def test_batch_includes_an_unsaved_draft_and_can_be_cancelled(workbench):
    w,app,_=workbench
    w.draft={'geometry':mapping(box(40,20,50,30)),'points':[],'pending':False}
    w.refresh_labels();before=copy.deepcopy(w.project['labels']);draft=copy.deepcopy(w.draft)
    draw(w,app,[[18,25],[52,25]])
    assert len(w.draft['reshape_batch'])==2 and not w.draft.get('base_id')
    assert '__draft' in w.view.overlay_records and 'target' in w.view.overlay_records
    w.undo_context();assert w.draft==draft and w.project['labels']==before
    w.redo_context();assert len(w.draft['reshape_batch'])==2
    QTest.keyClick(w.view.viewport(),Qt.Key.Key_Return);wait(w,app)
    assert not w.draft and len(w.project['labels'])==2 and len(w.label_undo)==1
    w.undo_label();assert w.project['labels']==before


def test_save_failure_does_not_publish_part_of_a_batch(workbench,monkeypatch):
    w,app,_=workbench;two_labels(w);draw(w,app,[[18,25],[52,25]])
    before=copy.deepcopy(w.project['labels']);errors=[]
    monkeypatch.setattr(w,'error',errors.append)
    # Force the second staged contour to be completely occupied by the first.
    w.draft['reshape_batch'][1]['geometry']=before[0]['geometry']
    w.confirm()
    assert errors and w.draft['reshape_batch'] and w.project['labels']==before and not w.label_undo
