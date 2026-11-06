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


def test_worker_failure_is_recorded_and_reported_in_status_bar(workbench,monkeypatch):
    from geoforma import reshape
    w,app,_=workbench;messages=[];before=copy.deepcopy(w.project['labels'])
    monkeypatch.setattr(w.statusBar(),'showMessage',lambda *args:messages.append(args))
    def fail(*args,**kwargs):raise ValueError('模拟重塑失败')
    monkeypatch.setattr(reshape,'reshape_geometry',fail)
    draw(w,app,OUT)
    assert w.project['labels']==before and w.reshape_session and w.reshape_session.get('error')
    assert '模拟重塑失败' in w.log.toPlainText()
    assert w.log.toPlainText().count('Traceback (most recent call last):')==1
    assert len([args for args in messages if args and '模拟重塑失败' in args[0]])==1


@pytest.mark.parametrize('auto',[False,True])
def test_cancelled_reshape_does_not_report_an_error(workbench,monkeypatch,auto):
    import threading
    from geoforma import reshape
    w,app,_=workbench;before=copy.deepcopy(w.project['labels']);started=threading.Event();messages=[]
    monkeypatch.setattr(w.statusBar(),'showMessage',lambda *args:messages.append(args))
    def pending(*args,**kwargs):
        task=args[7];started.set()
        while not task.cancel_event.wait(.01):task.check()
        task.check()
    monkeypatch.setattr(reshape,'reshape_geometry' if auto else 'reshape_raster',pending)
    if not auto:w.selected_id='target';w.selected_ids={'target'}
    w.begin_reshape(auto=auto)
    for x,y in OUT:w.add_reshape_point(x,y)
    w.finish_reshape();deadline=time.monotonic()+5
    while not started.is_set():app.processEvents();QTest.qWait(5);assert time.monotonic()<deadline
    w.cancel();wait(w,app)
    assert w.project['labels']==before and w.reshape_session and not w.reshape_session.get('error')
    assert not any(args and '任务已取消' in args[0] for args in messages)


def two_labels(w):
    w.project['labels'].append(dict(w.project['labels'][0],id='other',class_id=2,geometry=mapping(box(40,20,50,30))))
    w.project['classes'].append({'id':2,'name':'第二类','value':2,'color':'#00ff00'})
    w.refresh_labels()


def test_auto_reshape_worker_reuses_immutable_geometry_snapshots(workbench,monkeypatch):
    from types import SimpleNamespace
    from geoforma import reshape
    w,app,_=workbench;two_labels(w)
    target,other=w.project['labels'];geometries=(target['geometry'],other['geometry'])
    captured=[];work=[]
    def fake(image,geometry,stroke,blockers,bounds,single,alternate,task,include_holes=True,pixel_grid=False):
        captured.append((geometry,tuple(blockers),pixel_grid))
        return {'geometry':geometry}
    monkeypatch.setattr(reshape,'reshape_geometry',fake)
    monkeypatch.setattr(w,'run',lambda title,fn,*args,**kwargs:work.append(fn))
    w.begin_reshape(auto=True)
    for x,y in OUT:w.add_reshape_point(x,y)
    w.finish_reshape()
    assert len(work)==1
    work[0](SimpleNamespace(check=lambda:None))
    assert captured[0][0] is geometries[0] and captured[0][1][0] is geometries[1]
    assert captured[0][2] is True


def test_auto_target_scan_runs_off_ui_thread_and_cancellation_keeps_labels(workbench,monkeypatch):
    import threading
    from PySide6.QtCore import QTimer
    from geoforma.controllers import reshape as flow
    w,app,_=workbench;before=copy.deepcopy(w.project['labels'])
    started=threading.Event();release=threading.Event();processed=[];original=flow.shape
    main=threading.current_thread()
    def blocked(value):
        assert threading.current_thread() is not main, '目标识别不能阻塞界面线程'
        started.set();assert release.wait(5)
        return original(value)
    monkeypatch.setattr(flow,'shape',blocked)
    try:
        w.begin_reshape(auto=True)
        for x,y in OUT:w.add_reshape_point(x,y)
        w.finish_reshape()
        deadline=time.monotonic()+5
        while not started.is_set() and time.monotonic()<deadline:app.processEvents();QTest.qWait(2)
        assert started.is_set() and w.task is not None
        QTimer.singleShot(0,lambda:processed.append(True));app.processEvents()
        assert processed and w.task is not None
        w.cancel_reshape();release.set();wait(w,app)
        assert w.project['labels']==before and w.reshape_session is None
    finally:release.set()


def test_uncrossed_async_stroke_remains_editable(workbench):
    w,app,_=workbench;before=copy.deepcopy(w.project['labels']);w.begin_reshape(auto=True)
    for point in [[60,60],[70,70]]:w.add_reshape_point(*point)
    w.finish_reshape();wait(w,app)
    session=w.reshape_session
    assert session and '未穿过' in session['error'] and w.project['labels']==before and w.view.reshape_enabled
    assert w.progress.model.state.phase=='failed'
    w.add_reshape_point(80,80)
    assert len(session['stroke'])==3 and 'error' not in session


def test_auto_target_scan_does_not_commit_after_context_change(workbench,monkeypatch):
    import threading
    from geoforma.controllers import reshape as flow
    w,app,_=workbench;before=copy.deepcopy(w.project['labels'])
    started=threading.Event();release=threading.Event();original=flow.shape
    def blocked(value):
        started.set();assert release.wait(5)
        return original(value)
    monkeypatch.setattr(flow,'shape',blocked)
    try:
        w.begin_reshape(auto=True);session=w.reshape_session
        for x,y in OUT:w.add_reshape_point(x,y)
        w.finish_reshape();deadline=time.monotonic()+5
        while not started.is_set() and time.monotonic()<deadline:app.processEvents();QTest.qWait(2)
        assert started.is_set()
        w.project_epoch+=1;release.set();wait(w,app)
        assert w.project['labels']==before and w.reshape_session is session and not session.get('error')
        assert w.progress.model.state.phase=='cancelled'
    finally:release.set()


def test_cancel_reshape_discards_only_its_deferred_prefetch_work(workbench,monkeypatch):
    w,app,_=workbench;before=copy.deepcopy(w.project['labels']);callbacks=[]
    def defer(callback,allow_prompt_changes=False):
        w.pending_prefetch_work=(w.annotation_context(),callback,allow_prompt_changes)
        callbacks.append(callback);return True
    monkeypatch.setattr(w,'defer_for_prefetch',defer)
    w.begin_reshape(auto=True)
    for x,y in OUT:w.add_reshape_point(x,y)
    w.finish_reshape()
    assert len(callbacks)==1 and w.pending_prefetch_work is not None
    w.cancel_reshape()
    assert w.pending_prefetch_work is None and w.reshape_session is None
    assert w.view.reshape_enabled and w.project['labels']==before


def test_completed_deferred_scan_releases_its_pending_snapshot(workbench,monkeypatch):
    w,app,_=workbench;before=copy.deepcopy(w.project['labels'])
    def defer(callback,allow_prompt_changes=False):
        w.pending_prefetch_work=(w.annotation_context(),callback,allow_prompt_changes)
        return True
    monkeypatch.setattr(w,'defer_for_prefetch',defer)
    w.begin_reshape(auto=True);session=w.reshape_session
    for point in [[60,60],[70,70]]:w.add_reshape_point(*point)
    w.finish_reshape();pending=w.pending_prefetch_work
    assert session.get('_pending_prefetch') is pending
    w.pending_prefetch_work=None;monkeypatch.setattr(w,'defer_for_prefetch',lambda *args,**kwargs:False)
    pending[1]();wait(w,app)
    assert w.reshape_session is session and '未穿过' in session['error']
    assert '_pending_prefetch' not in session and w.project['labels']==before


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


def test_single_crossing_does_not_block_other_targets(workbench):
    w,app,_=workbench;two_labels(w);before=copy.deepcopy(w.project['labels'])
    # The last target is entered only once and is excluded from the edit.
    draw(w,app,[[18,25],[45,25]])
    assert w.reshape_session is None and not w.draft and w.label_undo
    assert w.project['labels'][0]!=before[0] and w.project['labels'][1]==before[1]


def test_uncrossed_stroke_reports_error_in_status_bar(workbench):
    w,app,_=workbench;before=copy.deepcopy(w.project['labels'])
    draw(w,app,[[60,60],[70,70]])
    assert w.reshape_session and '未穿过' in w.reshape_session['error']
    assert w.statusBar().currentMessage()==w.reshape_session['error']
    assert not hasattr(w,'reshape_info') and w.project['labels']==before and not w.draft


def test_unbound_stroke_survives_reopen(workbench):
    w,app,tmp=workbench;w.begin_reshape(auto=True);w.add_reshape_point(18,25);w.add_reshape_point(52,25)
    w.project_path=tmp/'stroke.gfm';w.save();w.cancel_reshape();w.open_project(w.project_path);wait(w,app)
    assert w.reshape_session['target']=='auto' and w.reshape_session['stroke']==[[18,25],[52,25]]




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






def test_reshape_does_not_depend_on_a_stale_presentation_index(workbench,monkeypatch):
    w,app,_=workbench;before=copy.deepcopy(w.project['labels'])
    monkeypatch.setattr(w,'presentation_labels',lambda *args:[])
    draw(w,app,OUT)
    assert w.reshape_session is None and w.project['labels']!=before


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
    assert shape(restored['labels'][0]['geometry']).equals(shape(w.project['labels'][0]['geometry']))
    assert shape(restored['labels'][0]['geometry']).area>shape(before[0]['geometry']).area
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
