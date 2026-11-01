from types import SimpleNamespace
import copy
import pytest
from shapely.geometry import box,mapping,shape
from geoforma.atomic_io import read_json
from geoforma.label_index import LabelIndex
from geoforma.label_history import replay_all,restore_entries
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
    saved,_=index.visible({'geometry':mapping(box(1,1,2,2))})
    assert saved[0]['geometry'] is not a['geometry'] and '_render_path' not in saved[0]


def test_label_index_preserves_raw_records_and_saved_ownership():
    labels=[record('saved',box(0,0,5,10)),record('candidate',box(0,0,10,10),'candidate')];original=copy.deepcopy(labels)
    index=LabelIndex(labels)
    assert shape(index.candidates[0]['geometry']).equals(box(5,0,10,10))
    assert labels==original


def test_large_index_can_cancel_before_constructing_all_shapes():
    calls=[]
    def check():calls.append(None);raise Cancelled()
    with pytest.raises(Cancelled):LabelIndex([record(str(i),box(i,0,i+1,1)) for i in range(100)],task=SimpleNamespace(check=check))
    assert len(calls)==1


def test_bulk_history_matches_ordered_replay_and_keeps_inputs_immutable():
    labels=[record('a',box(0,0,1,1)),record('b',box(2,0,3,1))]
    undo=[[('a',None,0)],[('b',None,1)]];original=copy.deepcopy(labels)
    task=SimpleNamespace(check=lambda:None,signals=SimpleNamespace(progress=SimpleNamespace(emit=lambda *a:None)))
    result=replay_all(labels,undo,[],[{'id':'one'}],task)
    assert not result['labels'] and result['dismissed']['one']==['a','b'] and labels==original
    restored=result['labels']
    for entries in reversed(result['redo']):restored,_=restore_entries(restored,entries)
    assert restored==original


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
