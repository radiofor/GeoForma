"""Reuse independent smoothing without reusing image or neighbor decisions."""
from shapely.geometry import box,mapping,shape
from geoforma.smoothing_cache import SmoothingGeometryCache
from geoforma import smoothing
from test_reshape import raster_image


def record(identifier,geometry):
    return {'id':identifier,'image_id':'image','status':'confirmed','geometry':mapping(geometry)}


def test_only_changed_geometries_are_smoothed_again(monkeypatch):
    cache=SmoothingGeometryCache();calls=[];original=smoothing._smooth_shape
    def counted(geometry,value,task):calls.append(geometry);return original(geometry,value,task)
    monkeypatch.setattr(smoothing,'_smooth_shape',counted)
    labels=[record('a',box(2,2,8,8)),record('b',box(15,2,21,8))]
    smoothing.smooth_batch(labels,1,cache=cache);assert len(calls)==2
    smoothing.smooth_batch(labels,1,cache=cache);assert len(calls)==2
    updated=[dict(labels[0],geometry=mapping(box(1,2,8,8))),labels[1]]
    cached=smoothing.smooth_batch(updated,1,cache=cache);assert len(calls)==3
    reference=smoothing.smooth_batch(updated,1)
    assert all(shape(a['geometry']).equals(shape(b['geometry'])) for a,b in zip(cached,reference))


def test_cached_shape_rechecks_bounds_and_neighbor_interactions():
    cache=SmoothingGeometryCache();labels=[record('a',box(2,2,12,12)),record('b',box(12,2,18,12))]
    smoothing.smooth_batch(labels,1,{'width':30,'height':30},cache=cache)
    changed=[labels[0],dict(labels[1],geometry=mapping(box(8,2,18,12)))]
    cached=smoothing.smooth_batch(changed,1,{'width':14,'height':14},cache=cache)
    fresh=smoothing.smooth_batch(changed,1,{'width':14,'height':14})
    assert all(shape(a['geometry']).equals(shape(b['geometry'])) for a,b in zip(cached,fresh))
    assert all(shape(item['geometry']).bounds[2]<=14 for item in cached)


def test_cleared_cache_rejects_late_worker_result():
    cache=SmoothingGeometryCache();source=mapping(box(0,0,3,3));raw=shape(source);epoch=cache.snapshot()
    cache.clear();cache.put(source,1,raw,raw,epoch)
    assert cache.get(source,1,epoch) is None and not cache.entries and cache.bytes==0


def test_large_batch_keeps_cached_hits_even_if_misses_precede_them(monkeypatch):
    cache=SmoothingGeometryCache(max_entries=1);calls=[];original=smoothing._smooth_shape
    def counted(geometry,value,task):calls.append(geometry);return original(geometry,value,task)
    monkeypatch.setattr(smoothing,'_smooth_shape',counted)
    labels=[record('a',box(2,2,8,8)),record('b',box(15,2,21,8)),record('c',box(28,2,34,8))]
    smoothing.smooth_batch(labels,1,cache=cache);assert len(calls)==3
    smoothing.smooth_batch(labels,1,cache=cache);assert len(calls)==5


def test_project_save_reuses_cached_geometry_without_changing_file_semantics(tmp_path,raster_image,monkeypatch):
    import copy,json
    from geoforma.domain import new_project
    from geoforma.storage import project_snapshot,save_project,load_project
    image=raster_image;labels=[dict(record('a',box(20,20,30,30)),image_id=image['id'],class_id=1)]
    project=new_project();project['images']=[image];project['labels']=labels
    snapshot=project_snapshot(project);before=copy.deepcopy(snapshot);cache=SmoothingGeometryCache()
    smoothing.smooth_batch(labels,1,image,cache=cache)
    calls=[];original=smoothing._smooth_shape
    def counted(*args):calls.append(1);return original(*args)
    monkeypatch.setattr(smoothing,'_smooth_shape',counted)
    cached_path=tmp_path/'cached.gfm';save_project(snapshot,cached_path,smoothing_cache=cache,cache_epoch=cache.snapshot())
    assert not calls and snapshot==before
    fresh_path=tmp_path/'fresh.gfm';save_project(snapshot,fresh_path)
    assert len(calls)==1
    cached=json.loads(cached_path.read_text(encoding='utf-8'))['labels'][0]
    fresh=json.loads(fresh_path.read_text(encoding='utf-8'))['labels'][0]
    assert shape(cached['geometry']).equals(shape(fresh['geometry']))
    assert cached['source_geometry']==fresh['source_geometry'] and shape(load_project(cached_path)['labels'][0]['geometry']).equals(shape(labels[0]['geometry']))


def test_stale_save_epoch_does_not_repopulate_geometry_cache(tmp_path,raster_image):
    from geoforma.domain import new_project
    from geoforma.storage import save_project
    project=new_project();project['images']=[raster_image]
    project['labels']=[dict(record('a',box(20,20,30,30)),image_id=raster_image['id'],class_id=1)]
    cache=SmoothingGeometryCache();old_epoch=cache.snapshot();cache.clear()
    save_project(project,tmp_path/'old.gfm',smoothing_cache=cache,cache_epoch=old_epoch)
    assert not cache.entries and cache.bytes==0
