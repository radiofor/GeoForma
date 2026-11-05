"""Direct strokes save confirmed targets and preserve independent drafts."""
import copy,time,json
import pytest
from PySide6.QtCore import Qt,QPointF
from PySide6.QtTest import QTest
from shapely.geometry import box,mapping,shape,MultiPolygon
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
def test_stroke_ignores_selection_and_saves_with_smoothing(workbench,selected):
    w,app,_=workbench
    w.project['labels'].append(dict(w.project['labels'][0],id='other',geometry=mapping(box(60,60,70,70))))
    w.selected_id=selected;w.selected_ids={selected} if selected else set();w.refresh_labels()
    before=copy.deepcopy(w.project['labels']);w.smooth_enabled.setChecked(True);settled(w,app)
    draw(w,app,OUT)
    assert not w.draft and w.project['labels']!=before
    assert all(row.status=='已保存' for row in w.label_presenter.rows)
    assert next(l for l in w.project['labels'] if l['id']=='other')==before[1]
    assert not shape(w.view.overlay_records['target'].geometry_value).equals(shape(next(l for l in w.project['labels'] if l['id']=='target')['geometry']))


def test_successful_reshape_does_not_show_a_status_prompt(workbench,monkeypatch):
    w,app,_=workbench;messages=[]
    monkeypatch.setattr(w.statusBar(),'showMessage',lambda *args:messages.append(args))
    draw(w,app,OUT)
    assert w.project['labels'][0]['editing_state']=='manual' and not any(args and args[0] for args in messages)


def test_worker_failure_is_recorded_without_a_status_prompt(workbench,monkeypatch):
    from geoforma import reshape
    w,app,_=workbench;messages=[];before=copy.deepcopy(w.project['labels'])
    monkeypatch.setattr(w.statusBar(),'showMessage',lambda *args:messages.append(args))
    def fail(*args,**kwargs):raise ValueError('模拟重塑失败')
    monkeypatch.setattr(reshape,'reshape_raster',fail)
    draw(w,app,OUT)
    assert w.project['labels']==before and w.reshape_session and w.reshape_session.get('error')
    assert '模拟重塑失败' in w.log.toPlainText() and not any(args and args[0] for args in messages)


def two_labels(w):
    w.project['labels'].append(dict(w.project['labels'][0],id='other',class_id=2,geometry=mapping(box(40,20,50,30))))
    w.project['classes'].append({'id':2,'name':'第二类','value':2,'color':'#00ff00'})
    w.refresh_labels()


def test_multiple_crossed_labels_save_and_undo_as_one_transaction(workbench):
    w,app,tmp=workbench;two_labels(w);before=copy.deepcopy(w.project['labels'])
    draw(w,app,[[18,25],[52,25]])
    assert not w.draft and w.project['labels']!=before
    assert all(row.status=='已保存' for row in w.label_presenter.rows)
    assert shape(w.view.overlay_records['other'].geometry_value).area<100
    # The automatic transaction and its undo survive reopening.
    w.project_path=tmp/'batch.gfm';w.save();w.open_project(w.project_path);wait(w,app)
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


def test_uncrossed_stroke_records_error_without_a_visible_prompt(workbench):
    w,app,_=workbench;before=copy.deepcopy(w.project['labels'])
    before_message=w.statusBar().currentMessage()
    draw(w,app,[[60,60],[70,70]])
    assert w.reshape_session and '未穿过' in w.reshape_session['error']
    assert w.statusBar().currentMessage()==before_message
    assert not hasattr(w,'reshape_info') and w.project['labels']==before and not w.draft


def test_unbound_stroke_survives_reopen(workbench):
    w,app,tmp=workbench;w.begin_reshape(auto=True);w.add_reshape_point(18,25);w.add_reshape_point(52,25)
    w.project_path=tmp/'stroke.gfm';w.save();w.cancel_reshape();w.open_project(w.project_path);wait(w,app)
    assert w.reshape_session['target']=='auto' and w.reshape_session['stroke']==[[18,25],[52,25]]


def test_batch_with_unsaved_draft_preserves_its_status_and_undo(workbench):
    w,app,_=workbench
    w.draft={'geometry':mapping(box(40,20,50,30)),'points':[],'pending':False}
    w.refresh_labels();before=copy.deepcopy(w.project['labels']);draft=copy.deepcopy(w.draft)
    draw(w,app,[[18,25],[52,25]])
    assert not w.draft.get('base_id') and w.project['labels']!=before
    assert shape(w.draft['geometry']).area<100
    assert sorted(row.status for row in w.label_presenter.rows)==['已保存','未保存']
    assert '__draft' in w.view.overlay_records and 'target' in w.view.overlay_records
    w.undo_context();assert w.draft==draft and w.project['labels']==before
    w.redo_context();assert w.project['labels']!=before and shape(w.draft['geometry']).area<100
    QTest.keyClick(w.view.viewport(),Qt.Key.Key_Return);wait(w,app)
    assert not w.draft and len(w.project['labels'])==2 and len(w.label_undo)==2
    w.undo_label();w.undo_label();assert w.project['labels']==before


def test_failure_does_not_publish_part_of_a_batch(workbench,monkeypatch):
    from geoforma import label_conflicts
    w,app,_=workbench;two_labels(w);before=copy.deepcopy(w.project['labels']);original=label_conflicts.resolve;calls=[]
    def fail_second(*args,**kwargs):
        calls.append(1)
        if len(calls)==2:raise ValueError('不能保存第二个目标')
        return original(*args,**kwargs)
    monkeypatch.setattr(label_conflicts,'resolve',fail_second)
    draw(w,app,[[18,25],[52,25]])
    assert w.reshape_session and '第二个目标' in w.reshape_session['error']
    assert w.project['labels']==before and not w.draft and not w.label_undo


def test_saved_target_can_be_reshaped_with_an_unrelated_unsaved_draft(workbench):
    w,app,_=workbench
    w.draft={'geometry':mapping(box(60,60,70,70)),'points':[[65,65,1]],'pending':False}
    w.refresh_labels();draft=copy.deepcopy(w.draft);before=copy.deepcopy(w.project['labels'])
    draw(w,app,OUT)
    assert w.draft==draft and w.project['labels']!=before
    assert sorted(row.status for row in w.label_presenter.rows)==['已保存','未保存']
    saved=copy.deepcopy(w.project['labels']);w.undo_context()
    assert w.draft==draft and w.project['labels']==before
    w.redo_context();assert w.draft==draft and w.project['labels']==saved


def test_reshape_automatically_writes_saved_project(workbench):
    from geoforma.storage import load_project
    w,app,tmp=workbench
    del w.autosave
    w.project_path=tmp/'automatic.gfm';w.save()
    before=copy.deepcopy(w.project['labels']);draw(w,app,OUT)
    deadline=time.monotonic()+8
    while w.autosave_task or w.project_saves.busy:
        app.processEvents();QTest.qWait(2);assert time.monotonic()<deadline
    restored=load_project(w.project_path)
    assert restored['labels']!=before
    assert restored['labels'][0]['status']=='confirmed'
    assert shape(restored['labels'][0]['geometry']).area==124
    assert not restored['workspace']['draft']


def test_disconnected_saved_result_creates_independent_undoable_rows(workbench):
    w,app,_=workbench;before=copy.deepcopy(w.project['labels']);w.single_polygon.setChecked(False)
    w.begin_reshape();session=w.reshape_session
    result={'geometry':mapping(MultiPolygon([box(20,20,24,30),box(26,20,30,30)])),
            'stroke':OUT,'alternate':False,'window':[20,20,10,10],'added_pixels':0,'removed_pixels':20}
    session['preview']=result;w.commit_reshape()
    assert len(w.project['labels'])==2 and len({item['id'] for item in w.project['labels']})==2
    assert all(item['geometry']['type']=='Polygon' and item['status']=='confirmed' for item in w.project['labels'])
    assert len(w.label_presenter.rows)==2 and all(row.status=='已保存' for row in w.label_presenter.rows)
    w.undo_context();assert w.project['labels']==before
    w.redo_context();assert len(w.project['labels'])==2
