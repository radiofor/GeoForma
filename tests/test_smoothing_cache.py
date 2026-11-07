"""Reuse independent smoothing without reusing image or neighbor decisions."""
from shapely.geometry import box,mapping,shape
from geoforma.smoothing_cache import SmoothingGeometryCache
from geoforma import smoothing
from test_reshape import raster_image


def record(identifier,geometry):
    return {'id':identifier,'image_id':'image','status':'confirmed','geometry':mapping(geometry)}


def test_stopping_releases_uncached_last_result_but_keeps_bounded_cache():
    from PySide6.QtWidgets import QApplication
    from geoforma.rendering.smoothing_queue import SmoothingQueue
    app=QApplication.instance() or QApplication([])
    queue=SmoothingQueue();cached=['small'];large=['large']
    queue.cache['small']=([],cached,128)
    queue.last=('large',[],large)
    queue.stop()
    assert queue.last is None and queue.cache['small'][1] is cached
    assert queue.request('small',[],lambda task:None) is cached
    queue.stop()
    assert queue.last[2] is cached
    queue.close()


def test_current_large_result_survives_switch_and_fill_variants():
    from PySide6.QtWidgets import QApplication
    from geoforma.rendering.smoothing_queue import SmoothingQueue
    app=QApplication.instance() or QApplication([]);queue=SmoothingQueue()
    context=('project','image','mode');queue.set_context(context)
    smooth=['large'];filled=['filled']
    queue.prime('smooth',[],smooth,retain=True,context=context)
    queue.stop()
    assert queue.request('smooth',[],lambda task:None,retain=True) is smooth
    queue.prime('fill-only',[],filled,retain=False,context=context)
    queue.stop()
    assert queue.request('smooth',[],lambda task:None,retain=True) is smooth
    queue.set_context(('project','other','mode'));queue.stop()
    assert queue.pinned is None and queue.last is None
    queue.close()


def test_retained_result_is_keyed_by_geometry_and_clear_drops_it():
    from PySide6.QtWidgets import QApplication
    from geoforma.rendering.smoothing_queue import SmoothingQueue
    app=QApplication.instance() or QApplication([]);queue=SmoothingQueue()
    context=('project','image','mode');queue.prime(('old',1),[],['old'],retain=True,context=context)
    queue.stop()
    assert queue.request(('new',2),[],lambda task:None,retain=True) is None
    queue.stop()
    assert queue.request(('old',1),[],lambda task:None,retain=True)==['old']
    queue.clear();assert queue.pinned is None and queue.last is None
    queue.close()


def test_retained_result_is_discarded_when_geometry_changes_or_is_deleted():
    from PySide6.QtWidgets import QApplication
    from geoforma.rendering.smoothing_queue import SmoothingQueue
    app=QApplication.instance() or QApplication([]);queue=SmoothingQueue()
    records=[record('a',box(2,2,8,8))]
    queue.prime('old',records,['old'],retain=True,context='image')
    queue.stop();queue.validate_pinned([dict(records[0])]);assert queue.pinned is not None
    changed=[dict(records[0],geometry=mapping(box(1,2,8,8)))]
    queue.validate_pinned(changed);assert queue.pinned is None and queue.last is None
    queue.prime('old',records,['old'],retain=True,context='image');queue.stop()
    queue.validate_pinned([]);assert queue.pinned is None and queue.last is None
    queue.close()


def test_real_oversized_worker_result_remains_available_after_toggle(monkeypatch):
    import time
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from geoforma.rendering import smoothing_queue
    app=QApplication.instance() or QApplication([]);queue=smoothing_queue.SmoothingQueue()
    monkeypatch.setattr(smoothing_queue,'prepare_paths',lambda records,value,task:value)
    ring=[(0,0)]*110000;geometry={'type':'Polygon','coordinates':[ring]}
    value=[{'geometry':geometry,'_source_geometry':geometry}];calls=[]
    queue.set_context(('project','image','mode'))
    queue.cache['other']=([],['retained'],128)
    def work(task):calls.append(1);return value
    queue.request('smooth',[],work,immediate=True,retain=True)
    deadline=time.monotonic()+5
    while queue.task is not None or queue.timer.isActive() or queue.pending:
        app.processEvents();QTest.qWait(2);assert time.monotonic()<deadline
    assert list(queue.cache)==['other'] and queue.last[2] is value
    queue.stop();assert queue.request('smooth',[],work,retain=True) is value
    assert calls==[1]
    queue.set_context(('project','other','mode'));queue.stop()
    assert queue.pinned is None and queue.last is None
    queue.close()


def test_context_change_releases_stale_result_after_running_worker_fails():
    import threading,time
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from geoforma.rendering.smoothing_queue import SmoothingQueue
    app=QApplication.instance() or QApplication([]);queue=SmoothingQueue()
    queue.prime('old',[],['large'],retain=True,context='image-a')
    started=threading.Event();release=threading.Event()
    def work(task):
        started.set();release.wait(5);raise ValueError('test')
    queue.request('new',[],work,immediate=True,retain=True)
    deadline=time.monotonic()+5
    try:
        while not started.is_set():app.processEvents();QTest.qWait(2);assert time.monotonic()<deadline
        queue.set_context('image-b');release.set()
        while queue.task is not None:app.processEvents();QTest.qWait(2);assert time.monotonic()<deadline
        assert queue.last is None and queue.pinned is None
    finally:release.set();queue.close()


def test_uncached_last_survives_result_signal_until_worker_finishes():
    import time
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from geoforma.rendering.smoothing_queue import SmoothingQueue
    app=QApplication.instance() or QApplication([]);queue=SmoothingQueue()
    records=[record('a',box(2,2,8,8))];observed=[]
    def stop_during_signal():
        queue.cache.clear();queue.stop()
    queue.updated.connect(stop_during_signal)
    queue.updated.connect(lambda:observed.append(queue.last[0]))
    queue.request('result',records,lambda task:records,immediate=True)
    deadline=time.monotonic()+5
    while queue.task is not None or queue.timer.isActive() or queue.pending:
        app.processEvents();QTest.qWait(2);assert time.monotonic()<deadline
    assert observed==['result'] and queue.last is None
    queue.close()


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


def test_project_save_never_computes_or_persists_smoothed_geometry(tmp_path,raster_image,monkeypatch):
    import copy,json
    import pytest
    from geoforma.domain import new_project
    from geoforma.storage import project_snapshot,save_project,load_project
    image=raster_image;labels=[dict(record('a',box(20,20,30,30)),image_id=image['id'],class_id=1)]
    project=new_project();project['images']=[image];project['labels']=labels
    snapshot=project_snapshot(project);before=copy.deepcopy(snapshot)
    monkeypatch.setattr(smoothing,'_smooth_shape',lambda *args:pytest.fail('项目保存不应计算平滑'))
    path=tmp_path/'project.gfm';save_project(snapshot,path)
    saved=json.loads(path.read_text(encoding='utf-8'))['labels'][0]
    assert snapshot==before and shape(saved['geometry']).equals(shape(labels[0]['geometry']))
    assert 'source_geometry' not in saved and 'smoothing_applied' not in saved
    assert shape(load_project(path)['labels'][0]['geometry']).equals(shape(labels[0]['geometry']))


def test_legacy_geometry_is_rejected_without_overwriting_current_geometry(tmp_path,raster_image):
    import json,pytest
    from geoforma.domain import new_project
    from geoforma.storage import save_project,load_project
    raw=mapping(box(20,20,30,30))
    project=new_project();project['images']=[raster_image]
    project['labels']=[dict(record('a',box(21,21,29,29)),image_id=raster_image['id'],class_id=1,
                            source_geometry=raw,smoothing_applied=1)]
    path=tmp_path/'existing.gfm';path.write_text(json.dumps(project),encoding='utf-8')
    before=path.read_bytes()
    with pytest.raises(ValueError,match='旧轮廓字段'):load_project(path)
    with pytest.raises(ValueError,match='旧轮廓字段'):save_project(project,path)
    assert path.read_bytes()==before


def test_saving_rejects_legacy_geometry_in_undo_history(tmp_path,raster_image):
    import copy,pytest
    from geoforma.domain import new_project
    from geoforma.storage import save_project
    project=new_project();project['images']=[raster_image]
    label=dict(record('a',box(20,20,30,30)),image_id=raster_image['id'],class_id=1)
    project['labels']=[label]
    previous=dict(copy.deepcopy(label),raw_geometry=copy.deepcopy(label['geometry']))
    project['history']={'schema':1,'labels':{'individual':{'undo':[[('a',previous,0)]],'redo':[]}}}
    path=tmp_path/'existing.gfm';path.write_bytes(b'existing')
    with pytest.raises(ValueError,match='旧轮廓字段'):save_project(project,path)
    assert path.read_bytes()==b'existing'
