from types import SimpleNamespace
import copy
import pytest
from shapely.geometry import box,mapping,shape
from geoforma.atomic_io import read_json
from geoforma.label_index import LabelIndex
from geoforma.label_history import restore_entries
from geoforma.prompt_bounds import MAX_PROMPT_POINTS
from geoforma.session_validation import validate_prompts
from geoforma.inference.engine import ModelEngine
from geoforma.tasks import Cancelled,Task


def test_json_limit_rejects_before_parsing_and_accepts_bom(tmp_path):
    path=tmp_path/'input.json';payload='{"value":"中文"}'.encode('utf-8-sig');path.write_bytes(payload)
    assert read_json(path,max_bytes=len(payload))=={'value':'中文'}
    with pytest.raises(ValueError,match='大小'):read_json(path,max_bytes=len(payload)-1)


@pytest.mark.parametrize('points',[[[float('nan'),1,1]],[[1,1,True]],[[1,1,1]]*(MAX_PROMPT_POINTS+1)])
def test_invalid_prompts_never_load_a_model(points):
    engine=ModelEngine();called=[];engine.prepare_backend=lambda *a:called.append(a)
    with pytest.raises(ValueError):engine.predict(None,{},dict(points=points,window=[0,0,1024,1024]),None)
    assert not called


def record(identifier,geometry,status='confirmed'):
    return dict(id=identifier,image_id='one',status=status,geometry=mapping(geometry),score=.9)


def test_clipping_invalidates_only_changed_render_paths():
    token=object();first=record('a',box(0,0,10,10));first.update(_render_path=token,_source_geometry=first['geometry'],_source_path=token)
    second=record('b',box(5,0,10,10));second['_render_path']=token
    index=LabelIndex([first,second]);a,b=index.confirmed
    assert shape(a['geometry']).equals(box(0,0,5,10))
    assert not any(key in a for key in ('_render_path','_source_geometry','_source_path'))
    assert b['_render_path'] is token and first['_render_path'] is token
    saved=index.visible({'geometry':mapping(box(1,1,2,2))})
    assert saved[0]['geometry'] is not a['geometry'] and '_render_path' not in saved[0]


def test_label_index_preserves_raw_records_and_saved_ownership():
    labels=[record('saved',box(0,0,5,10)),record('candidate',box(0,0,10,10),'candidate')];original=copy.deepcopy(labels)
    index=LabelIndex(labels)
    assert len(index.confirmed)==1 and index.visible()==index.confirmed
    assert labels==original


def test_draft_clipping_uses_spatial_index_and_preserves_unchanged_records(monkeypatch):
    import geoforma.label_index as module
    labels=[record(str(i),box(i*10,0,i*10+4,4)) for i in range(1000)]
    index=LabelIndex(labels);original_shape=module.shape;calls=[]
    def counted(value):
        calls.append(value);return original_shape(value)
    monkeypatch.setattr(module,'shape',counted)
    draft={'base_id':'0','geometry':mapping(box(11,0,13,4))}
    visible=index.visible(draft)
    assert len(calls)==1 and len(visible)==999
    assert visible[0]['id']=='1' and shape(visible[0]['geometry']).area==8
    assert visible[1] is index.confirmed[2]
    assert index.visible(draft) is visible and len(calls)==1


def test_draft_clipping_matches_geometry_for_holes_touching_and_covering():
    labels=[record('hole',box(0,0,10,10).difference(box(3,3,7,7))),
            record('touch',box(10,0,14,4)),record('covered',box(20,0,22,2))]
    index=LabelIndex(labels);draft=box(8,0,20,4).union(box(20,0,22,2))
    actual=index.visible({'geometry':mapping(draft)})
    expected=[(label,shape(label['geometry']).difference(draft)) for label in index.confirmed]
    expected=[(label,geometry) for label,geometry in expected if not geometry.is_empty]
    assert [label['id'] for label in actual]==[label['id'] for label,_ in expected]
    assert all(shape(result['geometry']).equals(geometry) for result,(_,geometry) in zip(actual,expected))


def test_spatial_tree_is_reused_when_saved_labels_need_no_clipping(monkeypatch):
    import geoforma.label_index as module
    original=module.STRtree;calls=[]
    def counted(geometries):
        calls.append(len(geometries));return original(geometries)
    monkeypatch.setattr(module,'STRtree',counted)
    index=LabelIndex([record('a',box(0,0,2,2)),record('b',box(5,0,7,2))])
    assert calls==[2]
    assert [item['id'] for item in index.visible({'geometry':mapping(box(1,0,6,2))})]==['a','b']
    calls.clear()
    clipped=LabelIndex([record('a',box(0,0,4,2)),record('b',box(2,0,6,2))])
    assert calls==[2,2] and shape(clipped.confirmed[0]['geometry']).area==4
    calls.clear()
    covered=LabelIndex([record('a',box(0,0,2,2)),record('b',box(0,0,2,2))])
    assert calls==[2,1] and [item['id'] for item in covered.confirmed]==['b']
    assert not covered.visible({'geometry':mapping(box(0,0,2,2))})


def test_model_change_indexes_saved_labels_once_for_multiple_drafts():
    from geoforma.controllers.modes import ModeWorkflow
    class Counted(list):
        scans=0
        def __iter__(self):
            self.scans+=1;return super().__iter__()
    labels=Counted([{'id':'manual','editing_state':'manual'},{'id':'model'}])
    manual={'base_id':'manual','points':[[1,1,1]]}
    staged={'base_id':'model','choices':[1],'logits':[1]}
    current={'points':[[2,2,1]]}
    image={'id':'one','mode_sessions':{'individual':{'draft':manual}}}
    workflow=ModeWorkflow();workflow.project={'labels':labels,'images':[image]}
    workflow.image=image;workflow.draft=current;workflow.image_sessions={('one','individual'):{'draft':staged}}
    workflow.invalidate_model_drafts()
    assert labels.scans==1 and manual=={'base_id':'manual','points':[[1,1,1]]}
    assert current['pending'] and staged['pending'] and 'choices' not in staged and 'logits' not in staged
    labels.scans=0;workflow.image_sessions={};image['mode_sessions']={}
    workflow.invalidate_model_drafts();assert labels.scans==0


def test_large_index_can_cancel_before_constructing_all_shapes():
    calls=[]
    def check():calls.append(None);raise Cancelled()
    with pytest.raises(Cancelled):LabelIndex([record(str(i),box(i,0,i+1,1)) for i in range(100)],task=SimpleNamespace(check=check))
    assert len(calls)==1




def test_task_releases_captured_inputs_after_completion():
    import weakref,gc
    class Payload:pass
    payload=Payload();reference=weakref.ref(payload)
    task=Task(lambda current,value=payload:None);del payload;task.run();gc.collect()
    assert reference() is None and task.fn is None


def test_compressed_feature_archives_are_rejected_before_torch_load(tmp_path,monkeypatch):
    import torch
    from zipfile import ZipFile,ZIP_DEFLATED
    from geoforma.feature_cache import load_features
    path=tmp_path/'bomb.pt'
    with ZipFile(path,'w',compression=ZIP_DEFLATED) as archive:archive.writestr('archive/data/0',b'0'*1024**2)
    monkeypatch.setattr(torch,'load',lambda *a,**kw:pytest.fail('compressed cache must not be deserialized'))
    assert load_features(path,1024) is None


def test_oversized_old_model_window_is_replaced_by_a_bounded_point_window():
    from geoforma.domain import prompt_window
    result=prompt_window([[100,100,1]],current=[0,0,50000,50000])
    assert max(result[2:])<=8192


def test_unresponsive_cancelled_worker_has_a_bounded_grace_period(monkeypatch):
    from geoforma.inference import client
    import threading
    service=client.ModelService();service.ready=True;service.cancel_event=threading.Event()
    cancelled=threading.Event();cancelled.set();closed=[]
    service.connection=SimpleNamespace(poll=lambda timeout:False)
    service.process=SimpleNamespace(is_alive=lambda:True)
    monkeypatch.setattr(service,'close',lambda:closed.append(True))
    times=iter((10.,16.));monkeypatch.setattr(client.time,'monotonic',lambda:next(times))
    with pytest.raises(RuntimeError,match='操作已取消'):
        service._receive(SimpleNamespace(cancel_event=cancelled))
    assert closed==[True] and service.cancel_event.is_set()


@pytest.mark.parametrize('field',['raw_geometry','source_geometry'])
@pytest.mark.parametrize('geometry',[{'type':'Point','coordinates':[1,2]}, {'type':'Polygon','coordinates':[]}])
def test_auxiliary_label_geometry_is_validated_before_indexing(field,geometry):
    from geoforma.project_validation import validate_label
    label=dict(record('invalid',box(0,0,10,10)),**{field:geometry})
    with pytest.raises(ValueError,match='多边形'):
        validate_label(label,{'one'})
