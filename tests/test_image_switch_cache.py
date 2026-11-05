"""Repeated image switches reuse bounded, correctly invalidated display work."""
from types import SimpleNamespace
import pytest
from shapely.geometry import box,mapping
from geoforma.label_index_cache import LabelIndexCache
from geoforma.rendering.path_cache import GeometryPathCache
from test_workbench import workbench,fake_image


def test_label_index_cache_enforces_lru_and_memory_limits():
    cache=LabelIndexCache(max_entries=2,max_bytes=10)
    a=SimpleNamespace(cache_weight=4);b=SimpleNamespace(cache_weight=4);c=SimpleNamespace(cache_weight=4)
    cache.put('a','a1',a);cache.put('b','b1',b);assert cache.get('a','a1') is a
    cache.put('c','c1',c);assert cache.get('b','b1') is None and cache.bytes==8
    assert cache.get('a','changed') is None and cache.bytes==4
    cache.put('huge','h',SimpleNamespace(cache_weight=11));assert cache.get('huge','h') is None
    cache.clear();assert not cache and cache.bytes==0


def test_geometry_path_cache_bounds_memory_and_checks_identity():
    cache=GeometryPathCache(max_entries=2,max_bytes=2304)
    a=mapping(box(0,0,1,1));b=mapping(box(1,1,2,2));c=mapping(box(2,2,3,3))
    cache.put(a,'a');cache.put(b,'b');assert cache.get(a)=='a'
    cache.put(c,'c');assert cache.get(b) is None and cache.get(a)=='a' and cache.get(c)=='c'
    assert cache.bytes<=2304
    cache.clear();assert len(cache)==0 and cache.bytes==0


def test_switch_back_reuses_label_index_and_rebuilds_after_edit(workbench,monkeypatch):
    from geoforma.controllers import label_list
    original=label_list.LabelIndex;built=[]
    def tracked(labels,task=None):
        result=original(labels,task);built.append(result);return result
    monkeypatch.setattr(label_list,'LabelIndex',tracked)
    w,app,wait,errors=workbench;w.request_render=lambda *args:None
    a,b=fake_image('a','a.tif'),fake_image('b','b.tif');w.project['images']=[a,b]
    w.project['labels']=[dict(id=f'{im["id"]}-{i}',image_id=im['id'],class_id=1,status='confirmed',geometry=mapping(box(i*3,0,i*3+2,2))) for im in (a,b) for i in range(36)]
    w.refresh_images();w.images.setCurrentRow(0);wait();first=w.label_index
    w.images.setCurrentRow(1);wait();second=w.label_index
    assert first is not second and len(built)==2
    w.images.setCurrentRow(0);wait();assert w.label_index is first and len(built)==2
    changed=w.project['labels'][0];w.project['labels']=[dict(row,class_id=2) if row is changed else row for row in w.project['labels']]
    w.refresh_labels();wait();assert w.label_index is not first and len(built)==3 and not errors


def test_index_signature_tracks_smoothing_relevant_metadata(workbench):
    w,app,wait,errors=workbench;image=fake_image('a','a.tif');w.project['images']=[image]
    record=dict(id='label',image_id='a',class_id=1,status='confirmed',geometry=mapping(box(1,1,9,9)),model={'single_polygon':False})
    w.project['labels']=[record];w.refresh_images();w.images.setCurrentRow(0);wait();first=w.label_index
    record['editing_state']='manual';record['box']=[0,0,10,10];record['model']['single_polygon']=True
    w.refresh_labels();wait();assert w.label_index is not first
    assert w.label_index.confirmed[0]['editing_state']=='manual' and w.label_index.confirmed[0]['model']['single_polygon'] and not errors


def test_duplicate_image_names_use_nearest_distinguishing_parent():
    from geoforma.ui.raster_presenter import build_raster_rows
    images=[dict(id='a',name='tile.tif',path='root/one/shared/tile.tif'),
            dict(id='b',name='tile.tif',path='root/two/shared/tile.tif'),
            dict(id='c',name='other.tif',path='root/three/other.tif')]
    rows=build_raster_rows(images)
    assert [row.title for row in rows]==['tile.tif · one','tile.tif · two','other.tif']


@pytest.mark.parametrize('changes',[{'model':None},{'model':{'single_polygon':'yes'}},{'box':'bad'},{'window':[0,0,-1,10]}])
def test_invalid_label_metadata_is_rejected_before_indexing(changes):
    from geoforma.label_validation import validate_label
    label=dict(id='one',image_id='a',status='confirmed',geometry=mapping(box(1,1,9,9)),**changes)
    with pytest.raises(ValueError):validate_label(label,{'a'})
