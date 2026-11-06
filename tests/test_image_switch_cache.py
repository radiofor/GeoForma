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


def test_switch_back_reuses_hidden_annotation_items_without_leaking_other_image(workbench):
    w,app,wait,errors=workbench;a,b=fake_image('a'),fake_image('b')
    w.project['images']=[a,b]
    w.project['labels']=[dict(id=im['id'],image_id=im['id'],class_id=1,status='confirmed',geometry=mapping(box(2,2,8,8))) for im in (a,b)]
    w.refresh_images();w.images.setCurrentRow(0);wait();first=w.view.overlay_records['a']
    w.images.setCurrentRow(1);wait();assert not first.isVisible() and set(w.view.overlay_records)=={'b'}
    second=w.view.overlay_records['b'];w.images.setCurrentRow(0);wait()
    assert w.view.overlay_records['a'] is first and first.isVisible() and not second.isVisible() and not errors


def test_empty_image_cancels_unneeded_previous_smoothing(workbench):
    w,app,wait,errors=workbench;image=fake_image('empty');w.project['images']=[image]
    w.project.setdefault('smoothing',{})[w.annotation_mode()]={'enabled':True,'value':1}
    w.refresh_images();w.images.setCurrentRow(0)
    w.smoother.key='old';w.smoother.pending=('old',[],lambda task:[])
    assert w.smooth_display([],None)==([],None)
    assert w.smoother.key is None and w.smoother.pending is None and not errors


def test_label_list_transition_fades_empty_and_nonempty_without_changing_identity(workbench):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    w,app,wait,errors=workbench;a,b=fake_image('a'),fake_image('b')
    w.project['images']=[a,b]
    w.project['labels']=[dict(id='one',image_id='a',class_id=1,status='confirmed',geometry=mapping(box(2,2,8,8)))]
    w.refresh_images();w.images.setCurrentRow(0);wait()
    transition=w.label_presenter.transition
    w.images.setCurrentRow(1)
    assert w.labels_table.rowCount()==0 and transition.old_frame.isVisible()
    w.images.setCurrentRow(0)
    assert w.labels_table.rowCount()==1 and transition.old_frame.isVisible()
    assert w.labels_table.item(0,0).data(256)=='one'
    QTest.mouseClick(w.labels_table.viewport(),Qt.MouseButton.LeftButton,pos=w.labels_table.visualItemRect(w.labels_table.item(0,0)).center());app.processEvents()
    assert not transition.old_frame.isVisible() and not errors


def test_label_list_rapid_switch_captures_current_opacity(workbench):
    w,app,wait,errors=workbench;a,b=fake_image('a'),fake_image('b')
    w.project['images']=[a,b];w.project['labels']=[dict(id='one',image_id='a',class_id=1,status='confirmed',geometry=mapping(box(2,2,8,8)))]
    w.refresh_images();w.images.setCurrentRow(0);wait();w.images.setCurrentRow(1);w.images.setCurrentRow(0)
    transition=w.label_presenter.transition;transition.old_frame.animation.pause();transition.old_frame._advance(.55);app.processEvents()
    before=w.labels_table.viewport().grab().toImage()
    transition.capture();after=transition.old_frame.frame.toImage()
    assert before==after and not errors
    transition.cancel()


def test_label_list_switch_keeps_visible_frame_over_new_rows(workbench):
    w,app,wait,errors=workbench;a,b=fake_image('a'),fake_image('b')
    w.project['images']=[a,b]
    w.project['labels']=[dict(id='one',image_id='a',class_id=1,status='confirmed',geometry=mapping(box(2,2,8,8)))]
    w.refresh_images();w.images.setCurrentRow(0);wait()
    w.select_label('one');app.processEvents()
    before=w.labels_table.viewport().grab().toImage()
    w.images.setCurrentRow(1);w.label_presenter.transition.old_frame.animation.pause();app.processEvents()
    assert w.labels_table.rowCount()==0
    assert w.labels_table.viewport().grab().toImage()==before
    assert w.labels_table.viewport().graphicsEffect() is None and not errors
    w.label_presenter.transition.cancel();app.processEvents()
    empty=w.labels_table.viewport().grab().toImage()
    w.images.setCurrentRow(0);w.label_presenter.transition.old_frame.animation.pause();app.processEvents()
    assert w.labels_table.rowCount()==1 and w.labels_table.viewport().grab().toImage()==empty
    assert not errors


def test_label_list_nonempty_switch_preserves_selected_frame_until_fade(workbench):
    w,app,wait,errors=workbench;a,b=fake_image('a'),fake_image('b')
    w.project['images']=[a,b]
    w.project['classes'].append({'id':2,'name':'其他类别'});w.refresh_classes()
    w.project['labels']=[dict(id='one',image_id='a',class_id=1,status='confirmed',geometry=mapping(box(2,2,8,8))),
                         dict(id='two',image_id='b',class_id=2,status='confirmed',geometry=mapping(box(20,20,28,28)))]
    w.refresh_images();w.images.setCurrentRow(0);wait();w.select_label('one')
    w.label_presenter.transition.cancel();app.processEvents()
    before=w.labels_table.viewport().grab().toImage()
    w.images.setCurrentRow(1);w.label_presenter.transition.old_frame.animation.pause();app.processEvents()
    assert w.label_presenter.rows[0].identifier=='two' and not w.label_presenter.rows[0].selected
    assert w.labels_table.viewport().grab().toImage()==before
    assert w.labels_table.viewport().graphicsEffect() is None and not errors


def test_uncached_image_keeps_current_display_until_overview_is_ready(workbench):
    import threading,time
    import numpy as np
    w,app,wait,errors=workbench;a,b=fake_image('a'),fake_image('b')
    for image in (a,b):image['display_recipe']={'bands':[1,2,3]}
    w.project['images']=[a,b];w.refresh_images();w.images.setCurrentRow(0)
    w.view.show_raster(np.zeros((3,3,3),np.uint8),np.ones((3,3),bool),(0,0,2000,2000),True)
    old=w.view.base_item;started=threading.Event();release=threading.Event()
    def read(*args):
        started.set();assert release.wait(3)
        return np.full((3,3,3),30,np.uint8),np.ones((3,3),bool)
    w.raster_renderer.reader=read
    try:
        w.images.setCurrentRow(1)
        end=time.monotonic()+3
        while not started.is_set() and time.monotonic()<end:app.processEvents();time.sleep(.002)
        assert started.is_set() and w.image is a and w.images.currentRow()==0 and w.view.base_item is old
        release.set()
        while w.image is not b and time.monotonic()<end:app.processEvents();time.sleep(.002)
        assert w.image is b and w.images.currentRow()==1
        assert w.raster_renderer.has_cached(b,[0,0,2000,2000],1400) and not errors
    finally:release.set()


def test_pending_image_switch_drops_obsolete_request_and_keeps_latest(workbench):
    import threading,time
    import numpy as np
    w,app,wait,errors=workbench;images=[fake_image(name) for name in ('a','b','c')]
    for image in images:image['display_recipe']={'bands':[1,2,3]}
    w.project['images']=images;w.refresh_images();w.images.setCurrentRow(0)
    w.view.show_raster(np.zeros((3,3,3),np.uint8),np.ones((3,3),bool),(0,0,2000,2000),True)
    started=threading.Event();release=threading.Event();reads=[]
    def read(image,*args):
        reads.append(image['id'])
        if image['id']=='b':started.set();assert release.wait(3)
        return np.zeros((3,3,3),np.uint8),np.ones((3,3),bool)
    w.raster_renderer.reader=read
    try:
        w.images.setCurrentRow(1);end=time.monotonic()+4
        while not started.is_set() and time.monotonic()<end:app.processEvents();time.sleep(.002)
        assert started.is_set();w.images.setCurrentRow(2);release.set()
        while w.image is not images[2] and time.monotonic()<end:app.processEvents();time.sleep(.002)
        assert w.image is images[2] and w.images.currentRow()==2 and reads==['b','c'] and not errors
        assert not w.raster_renderer.has_cached(images[1],[0,0,2000,2000],1400)
    finally:release.set()


def test_pending_switch_does_not_interrupt_new_edits(workbench):
    import threading,time
    import numpy as np
    w,app,wait,errors=workbench;a,b=fake_image('a'),fake_image('b')
    for image in (a,b):image['display_recipe']={'bands':[1,2,3]}
    w.project['images']=[a,b];w.refresh_images();w.images.setCurrentRow(0)
    w.view.show_raster(np.zeros((3,3,3),np.uint8),np.ones((3,3),bool),(0,0,2000,2000),True)
    started=threading.Event();release=threading.Event()
    def read(*args):
        started.set();assert release.wait(3)
        return np.zeros((3,3,3),np.uint8),np.ones((3,3),bool)
    w.raster_renderer.reader=read
    try:
        w.images.setCurrentRow(1);end=time.monotonic()+4
        while not started.is_set() and time.monotonic()<end:app.processEvents();time.sleep(.002)
        assert started.is_set();w.add_manual_vertex(100,100);assert w.draft.get('manual_vertices')==[[100,100]];release.set()
        while getattr(w,'_image_switch_task',None) is not None and time.monotonic()<end:app.processEvents();time.sleep(.002)
        assert w.image is a and w.images.currentRow()==0 and not errors
    finally:release.set()


def test_preparation_completion_does_not_cancel_pending_switch(workbench,monkeypatch):
    import threading,time
    import numpy as np
    w,app,wait,errors=workbench;a,b=fake_image('a'),fake_image('b')
    for image in (a,b):image['display_recipe']={'bands':[1,2,3]}
    w.project['images']=[a,b];w.refresh_images();w.images.setCurrentRow(0)
    w.view.show_raster(np.zeros((3,3,3),np.uint8),np.ones((3,3),bool),(0,0,2000,2000),True)
    started=threading.Event();release=threading.Event();callbacks={}
    def read(*args):
        started.set();assert release.wait(3)
        return np.zeros((3,3,3),np.uint8),np.ones((3,3),bool)
    w.raster_renderer.reader=read
    monkeypatch.setattr(w,'ensure_model_resources',lambda:True)
    monkeypatch.setattr(w,'record_runtime',lambda result:None)
    monkeypatch.setattr(w,'run',lambda title,work,done,**kwargs:callbacks.update(done=done))
    try:
        w.start_preparation(b);w.images.setCurrentRow(1);end=time.monotonic()+4
        while not started.is_set() and time.monotonic()<end:app.processEvents();time.sleep(.002)
        assert started.is_set();revision=w.dirty_revision
        callbacks['done']({'count':1,'hits':1})
        assert w.dirty_revision>revision and b['ready']
        release.set()
        while w.image is not b and time.monotonic()<end:app.processEvents();time.sleep(.002)
        assert w.image is b and w.images.currentRow()==1 and not errors
    finally:release.set()


def test_pending_switch_reloads_changed_target_display_settings(workbench):
    import threading,time
    import numpy as np
    w,app,wait,errors=workbench;a,b=fake_image('a'),fake_image('b')
    for image in (a,b):image['display_recipe']={'bands':[1,2,3]}
    w.project['images']=[a,b];w.refresh_images();w.images.setCurrentRow(0)
    w.view.show_raster(np.zeros((3,3,3),np.uint8),np.ones((3,3),bool),(0,0,2000,2000),True)
    started=threading.Event();release=threading.Event();reads=[]
    def read(image,*args):
        reads.append(image['display_recipe']['bands'][:])
        if len(reads)==1:started.set();assert release.wait(3)
        return np.zeros((3,3,3),np.uint8),np.ones((3,3),bool)
    w.raster_renderer.reader=read
    try:
        w.images.setCurrentRow(1);end=time.monotonic()+4
        while not started.is_set() and time.monotonic()<end:app.processEvents();time.sleep(.002)
        assert started.is_set();b['display_recipe']={'bands':[3,2,1]};release.set()
        while w.image is not b and time.monotonic()<end:app.processEvents();time.sleep(.002)
        assert w.image is b and reads==[[1,2,3],[3,2,1]]
        assert w.raster_renderer.has_cached(b,[0,0,2000,2000],1400) and not errors
    finally:release.set()


def test_frame_transition_is_short_and_immediately_interruptible(workbench):
    import numpy as np
    from PySide6.QtCore import QEvent
    from PySide6.QtTest import QTest
    w,app,wait,errors=workbench
    w.view.set_image(20,20)
    w.view.show_raster(np.zeros((4,4,3),np.uint8),np.ones((4,4),bool),(0,0,20,20),True)
    transition=w.view.frame_transition;transition.capture();transition.reveal()
    assert transition.isVisible() and transition.animation.duration()==300
    assert not transition.eventFilter(w.view.viewport(),QEvent(QEvent.Type.MouseButtonPress))
    assert not transition.isVisible() and transition.frame is None
    transition.capture();transition.reveal();QTest.qWait(340);app.processEvents()
    assert not transition.isVisible() and transition.frame is None and not errors


def test_new_transition_captures_the_current_blended_frame(workbench):
    import numpy as np
    w,app,wait,errors=workbench;w.view.set_image(20,20)
    valid=np.ones((20,20),bool);old=np.full((20,20,3),20,np.uint8);new=np.full((20,20,3),220,np.uint8)
    w.view.show_raster(old,valid,(0,0,20,20),True);app.processEvents()
    transition=w.view.frame_transition;transition.capture()
    w.view.show_raster(new,valid,(0,0,20,20),True);transition.reveal()
    transition.animation.pause();transition._advance(.5);app.processEvents()
    x=w.view.viewport().width()//2;y=w.view.viewport().height()//2
    before=w.view.viewport().grab().toImage().pixelColor(x,y).red()
    transition.capture();after=transition.frame.toImage().pixelColor(x,y).red()
    assert 20<before<220 and abs(before-after)<=1 and not errors
    transition.cancel()


def test_index_reuses_geometry_when_only_model_metadata_changes(workbench):
    w,app,wait,errors=workbench;image=fake_image('a','a.tif');w.project['images']=[image]
    record=dict(id='label',image_id='a',class_id=1,status='confirmed',geometry=mapping(box(1,1,9,9)),model={'single_polygon':False})
    w.project['labels']=[record];w.refresh_images();w.images.setCurrentRow(0);wait();first=w.label_index
    record['editing_state']='manual';record['box']=[0,0,10,10];record['model']['single_polygon']=True
    w.refresh_labels();wait();assert w.label_index is first
    record['class_id']=2;w.refresh_labels();wait();assert w.label_index is not first
    second=w.label_index;record['geometry']=mapping(box(1,1,10,10))
    w.refresh_labels();wait();assert w.label_index is not second and not errors


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
