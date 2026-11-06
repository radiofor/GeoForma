"""No-op targets do not prevent valid edits in the same transaction."""
import copy
import pytest

from shapely.geometry import box,mapping,shape
from test_reshape import workbench,raster_image
from test_reshape_auto import wait
from test_smoothing import settled


STROKE=[[9,19],[11,20.2],[19,20.2],[21,19],[29,19],[31,19],
        [31,22],[39,22],[39,19],[41,19]]


def setup_labels(w,app):
    first=w.project['labels'][0]
    first.update(source='interactive',geometry=mapping(box(10,10,20,20)))
    w.project['labels'].append(dict(first,id='second',geometry=mapping(box(30,10,40,20))))
    w.fill_holes.setChecked(False);w.smooth_enabled.setChecked(False)
    w.refresh_labels();settled(w,app)


def submit(w,app,stroke=STROKE):
    w.begin_reshape(auto=True)
    for point in stroke:w.add_reshape_point(*point)
    w.finish_reshape();wait(w,app)


def test_unchanged_target_is_skipped_and_changed_target_is_undoable(workbench):
    w,app,_=workbench;setup_labels(w,app);before=copy.deepcopy(w.project['labels'])
    submit(w,app)
    assert w.reshape_session is None
    assert shape(w.project['labels'][0]['geometry']).equals(shape(before[0]['geometry']))
    assert shape(w.project['labels'][1]['geometry']).area==114
    w.undo_label();assert w.project['labels']==before


def test_all_unchanged_targets_report_error_without_creating_history(workbench):
    w,app,_=workbench;setup_labels(w,app);before=copy.deepcopy(w.project['labels'])
    submit(w,app,STROKE[:4])
    assert w.project['labels']==before and not w.label_undo
    assert w.reshape_session and '未改变任何像元' in w.reshape_session.get('error','')


def test_real_error_after_first_result_keeps_entire_batch_unchanged(workbench,monkeypatch):
    from geoforma import reshape
    w,app,_=workbench;setup_labels(w,app);before=copy.deepcopy(w.project['labels'])
    actual=reshape.reshape_geometry;calls=[]
    def fail_second(*args,**kwargs):
        calls.append(1)
        if len(calls)==2:raise ValueError('测试几何错误')
        return actual(*args,**kwargs)
    monkeypatch.setattr(reshape,'reshape_geometry',fail_second)
    stroke=[[9,19],[11,19],[11,22],[19,22],[19,19],[21,19],
            [29,19],[31,19],[31,22],[39,22],[39,19],[41,19]]
    submit(w,app,stroke)
    assert len(calls)==2 and w.project['labels']==before and not w.label_undo
    assert w.reshape_session and w.reshape_session.get('error')


def test_source_checked_once_before_and_once_after_batch(workbench,monkeypatch):
    from geoforma import reshape
    w,app,_=workbench;setup_labels(w,app);calls=[]
    actual=reshape.validate_reshape_source
    def verify(*args,**kwargs):calls.append(1);return actual(*args,**kwargs)
    monkeypatch.setattr(reshape,'validate_reshape_source',verify)
    submit(w,app)
    assert len(calls)==2 and w.reshape_session is None


def test_source_changed_during_batch_cannot_commit_results(workbench,monkeypatch):
    from geoforma import reshape
    w,app,_=workbench;setup_labels(w,app);before=copy.deepcopy(w.project['labels']);calls=[]
    actual=reshape.validate_reshape_source
    def verify(*args,**kwargs):
        calls.append(1)
        if len(calls)==2:raise ValueError('影像源已变化')
        return actual(*args,**kwargs)
    monkeypatch.setattr(reshape,'validate_reshape_source',verify)
    submit(w,app)
    assert len(calls)==2 and w.project['labels']==before and not w.label_undo
    assert w.reshape_session and w.reshape_session.get('error')


def test_stroke_missing_all_targets_does_not_open_source(workbench,monkeypatch):
    from geoforma import reshape
    w,app,_=workbench;setup_labels(w,app);calls=[]
    monkeypatch.setattr(reshape,'validate_reshape_source',lambda *args,**kwargs:calls.append(1))
    submit(w,app,[[60,60],[70,70]])
    assert not calls and w.reshape_session and w.reshape_session.get('error')


def test_shared_edge_can_move_between_targets_and_undo_together(workbench):
    w,app,_=workbench;setup_labels(w,app)
    w.project['labels'][1]['geometry']=mapping(box(20,10,30,20))
    w.refresh_labels();settled(w,app);before=copy.deepcopy(w.project['labels'])
    submit(w,app,[[21,12],[18,12],[18,18],[21,18]])
    a,b=[shape(label['geometry']) for label in w.project['labels']]
    assert w.reshape_session is None and a.area==88 and b.area==112
    assert a.intersection(b).area==0
    after=copy.deepcopy(w.project['labels'])
    w.undo_label();assert w.project['labels']==before
    w.redo_label();assert w.project['labels']==after


def test_shared_edge_can_move_when_expanding_target_is_encountered_first(workbench):
    w,app,_=workbench;setup_labels(w,app)
    w.project['labels'][1]['geometry']=mapping(box(20,10,30,20))
    w.project['labels']=list(reversed(w.project['labels']));w.refresh_labels();settled(w,app)
    before=copy.deepcopy(w.project['labels'])
    submit(w,app,[[21,12],[18,12],[18,18],[21,18]])
    by_id={label['id']:shape(label['geometry']) for label in w.project['labels']}
    assert w.reshape_session is None and by_id['target'].area==88 and by_id['second'].area==112
    assert by_id['target'].intersection(by_id['second']).area==0
    after=copy.deepcopy(w.project['labels'])
    w.undo_label();assert w.project['labels']==before
    w.redo_label();assert w.project['labels']==after


def test_deferred_targets_retry_across_multiple_dependency_rounds(workbench,monkeypatch):
    from geoforma import reshape
    from geoforma.controllers import reshape as workflow
    w,app,_=workbench;setup_labels(w,app)
    a=w.project['labels'][0];b=w.project['labels'][1]
    b['geometry']=mapping(box(20,10,30,20))
    c=dict(a,id='third',geometry=mapping(box(30,10,40,20)))
    w.project['labels']=[c,b,a];w.refresh_labels();settled(w,app)
    before=copy.deepcopy(w.project['labels']);attempts=[];checks=[]
    real_validate=reshape.validate_reshape_source
    def verify(*args,**kwargs):checks.append(1);return real_validate(*args,**kwargs)
    monkeypatch.setattr(reshape,'validate_reshape_source',verify)
    monkeypatch.setattr(workflow,'_crosses_ring',lambda *args:True)
    def compute(image,geometry,stroke,blockers,*args,**kwargs):
        original=shape(geometry);left=original.bounds[0];attempts.append(left)
        if left==10:result=original.difference(box(18,12,20,18))
        elif left==20:result=original.union(box(18,12,20,18)).difference(box(28,12,30,18))
        else:result=original.union(box(28,12,30,18))
        from shapely.ops import unary_union
        blocked=result.intersection(unary_union([shape(g) for g in blockers]))
        if blocked.area>0:
            raise reshape.ReshapeNoChange('未改变任何像元',blocked_geometry=mapping(blocked))
        return {'geometry':mapping(result),'stroke':stroke,'alternate':False,'window':[0,0,1,1],
                'added_pixels':1,'removed_pixels':1}
    monkeypatch.setattr(reshape,'reshape_geometry',compute)
    submit(w,app,[[9,15],[41,15]])
    assert attempts==[30,20,10,20,30] and len(checks)==2
    assert w.reshape_session is None and len(w.label_undo)==1
    for label in w.project['labels']:
        assert shape(label['geometry']).is_valid
    w.undo_label();assert w.project['labels']==before


@pytest.mark.parametrize('source',['interactive','manual_draw'])
def test_partial_expansion_retries_after_neighbor_releases_space(workbench,source):
    w,app,_=workbench;setup_labels(w,app)
    for label in w.project['labels']:label['source']=source
    w.project['labels'][1]['geometry']=mapping(box(20,10,30,20))
    w.project['labels']=list(reversed(w.project['labels']));w.refresh_labels();settled(w,app)
    before=copy.deepcopy(w.project['labels'])
    stroke=[[21,12],[18,12],[18,18],[21,18],[21,22],[25,22],[25,18]]
    submit(w,app,stroke)
    by_id={label['id']:shape(label['geometry']) for label in w.project['labels']}
    assert w.reshape_session is None and by_id['target'].area==88 and by_id['second'].area==118
    assert by_id['target'].intersection(by_id['second']).area==0
    after=copy.deepcopy(w.project['labels'])
    w.undo_label();assert w.project['labels']==before
    w.redo_label();assert w.project['labels']==after


def test_atomic_commit_rejects_even_tiny_positive_overlap(workbench):
    w,app,_=workbench;setup_labels(w,app)
    w.project['labels'][1]['geometry']=mapping(box(20,10,30,20))
    w.refresh_labels();settled(w,app);before=copy.deepcopy(w.project['labels'])
    session={'label':{'id':'__stroke'},'target':'auto','context':w.annotation_context(),
             'stroke':[],'alternate':False,'preview':None}
    w.reshape_session=session
    def record(geometry):
        return {'geometry':mapping(geometry),'stroke':[[20,12],[18,18]],'alternate':False,
                'window':[0,0,1,1],'added_pixels':1,'removed_pixels':1}
    candidates=[record(box(10,10,20,20)),record(box(20-1e-12,10,30,20))]
    w.apply_reshape_results(session,[('label',label) for label in before],candidates)
    assert w.project['labels']==before and not w.label_undo
    assert w.reshape_session and w.reshape_session.get('error')


@pytest.mark.parametrize('failure',['error','cancel','regression'])
def test_retry_failure_or_regression_does_not_commit_any_target(workbench,monkeypatch,failure):
    from geoforma import reshape
    w,app,_=workbench;setup_labels(w,app)
    w.project['labels'][1]['geometry']=mapping(box(20,10,30,20))
    w.project['labels']=list(reversed(w.project['labels']));w.refresh_labels();settled(w,app)
    before=copy.deepcopy(w.project['labels']);actual=reshape.reshape_geometry;calls=[]
    def compute(image,geometry,stroke,blockers,bounds,single,alternate,task,**kwargs):
        calls.append(shape(geometry).bounds[0])
        if calls==[20,10,20]:
            if failure=='cancel':task.cancel();task.check()
            if failure=='error':raise ValueError('测试重试失败')
            result=actual(image,geometry,stroke,blockers,bounds,single,alternate,task,**kwargs)
            result['geometry']=geometry
            return result
        return actual(image,geometry,stroke,blockers,bounds,single,alternate,task,**kwargs)
    monkeypatch.setattr(reshape,'reshape_geometry',compute)
    submit(w,app,[[21,12],[18,12],[18,18],[21,18],[21,22],[25,22],[25,18]])
    assert calls==[20,10,20] and w.project['labels']==before and not w.label_undo
