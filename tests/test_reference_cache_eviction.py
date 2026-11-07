import threading
import time
import numpy as np
from PySide6.QtCore import QThreadPool
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication
from geoforma.reference_images import display_descriptor
from geoforma.rendering.raster_queue import RasterRenderQueue,reference_source
from test_workbench import workbench,fake_image


def test_removed_reference_evicts_only_unshared_decoded_and_pixmap_cache(workbench,monkeypatch):
    w,app,wait,errors=workbench
    base=fake_image('base','tile.tif');other=fake_image('other','other.tif')
    one=dict(base,group='one',fingerprint='reference-one');shared=dict(base,group='two',fingerprint='shared');shared_again=dict(other,group='two',fingerprint='shared')
    w.project['images']=[base,other];w.project['references']=[one,shared,shared_again];w.refresh_images();w.images.setCurrentRow(0)
    monkeypatch.setattr(w,'request_render',lambda *args:None)
    window=[0,0,4,4]
    def value():return np.zeros((4,4,3),np.uint8),np.ones((4,4),bool)
    main=value();gone=value();kept=value()
    q=w.raster_renderer
    for descriptor,v in ((base,main),(display_descriptor(base,one),gone),(display_descriptor(base,shared),kept)):
        q.prime(descriptor,window,4,v);w.view.layers.pixmap_cache.put(*v,QPixmap(4,4),reference_source(descriptor.get('_reference')))
    orphan=value();orphan[0].setflags(write=False);orphan[1].setflags(write=False)
    w.view.layers.pixmap_cache.put(*orphan,QPixmap(4,4),reference_source(one))
    before=q.cache_bytes
    renamed=dict(one,group='renamed');w.replace_references([renamed,shared,shared_again])
    assert q.has_cached(display_descriptor(base,one),window,4) and q.cache_bytes==before
    w.replace_references([shared_again])
    assert not q.has_cached(display_descriptor(base,one),window,4)
    assert q.has_cached(base,window,4) and q.has_cached(display_descriptor(base,shared),window,4)
    assert len(w.view.layers.pixmap_cache)==2 and q.cache_bytes==before-sum(a.nbytes for a in gone)
    w.replace_references([shared_again,one])
    assert not q.has_cached(display_descriptor(base,one),window,4)


def test_removed_reference_cannot_repopulate_cache_after_inflight_read():
    app=QApplication.instance() or QApplication([]);pool=QThreadPool();start=threading.Event();release=threading.Event()
    def reader(*args):
        start.set();release.wait(5)
        return np.zeros((3,3,3),np.uint8),np.ones((3,3),bool)
    q=RasterRenderQueue(pool,reader);base=fake_image('base','tile.tif');ref=dict(base,group='one',fingerprint='ref')
    descriptor=display_descriptor(base,ref);window=[0,0,3,3];published=[];q.rendered.connect(lambda *args:published.append(args))
    try:
        q.request(descriptor,1,window,3);deadline=time.monotonic()+5
        while not start.is_set():app.processEvents();time.sleep(.005);assert time.monotonic()<deadline
        q.evict_references({reference_source(ref)});q.request(descriptor,1,window,3);release.set()
        while q.task is not None:app.processEvents();time.sleep(.005);assert time.monotonic()<deadline
        assert q.has_cached(descriptor,window,3) and len(published)==1 and q.reads==2
    finally:release.set();q.close();pool.waitForDone()


def test_removed_reference_cancels_pending_but_keeps_active_main_read():
    app=QApplication.instance() or QApplication([]);pool=QThreadPool();start=threading.Event();release=threading.Event();reads=[]
    def reader(im,*args):
        reads.append(im);start.set();release.wait(5)
        return np.zeros((3,3,3),np.uint8),np.ones((3,3),bool)
    q=RasterRenderQueue(pool,reader);base=fake_image('base','tile.tif');ref=dict(base,group='one',fingerprint='ref')
    descriptor=display_descriptor(base,ref);window=[0,0,3,3]
    try:
        q.request(base,1,window,3);deadline=time.monotonic()+5
        while not start.is_set():app.processEvents();time.sleep(.005);assert time.monotonic()<deadline
        q.request(descriptor,1,window,3);assert q.pending_detail is not None
        q.evict_references({reference_source(ref)});assert q.pending_detail is None
        release.set()
        while q.task is not None:app.processEvents();time.sleep(.005);assert time.monotonic()<deadline
        assert len(reads)==1 and q.has_cached(base,window,3) and not q.has_cached(descriptor,window,3)
    finally:release.set();q.close();pool.waitForDone()


def test_shared_pixmap_survives_until_all_reference_sources_removed():
    from geoforma.rendering.pixmap_cache import RasterPixmapCache
    app=QApplication.instance() or QApplication([]);cache=RasterPixmapCache()
    array=np.zeros((3,3,3),np.uint8);valid=np.ones((3,3),bool)
    array.setflags(write=False);valid.setflags(write=False)
    cache.put(array,valid,QPixmap(3,3),'reference-a')
    assert cache.get(array,valid,'reference-b') is not None
    cache.evict_references({'reference-a'});assert cache.get(array,valid,'reference-b') is not None
    cache.evict_references({'reference-b'});assert len(cache)==0


def test_same_file_different_display_recipe_only_evicts_removed_recipe(workbench,monkeypatch):
    w,app,wait,errors=workbench
    base=fake_image('base','tile.tif');first=dict(base,group='first',fingerprint='shared-file',display_recipe={'bands':[1,2,3]})
    second=dict(first,group='second',display_recipe={**first['display_recipe'],'bands':[3,2,1]})
    w.project['images']=[base];w.project['references']=[first,second];w.refresh_images();w.images.setCurrentRow(0)
    monkeypatch.setattr(w,'request_render',lambda *args:None)
    window=[0,0,3,3]
    a=(np.zeros((3,3,3),np.uint8),np.ones((3,3),bool));b=(np.zeros((3,3,3),np.uint8),np.ones((3,3),bool))
    q=w.raster_renderer
    for ref,value in ((first,a),(second,b)):
        q.prime(display_descriptor(base,ref),window,3,value)
        w.view.layers.pixmap_cache.put(*value,QPixmap(3,3),reference_source(ref))
    w.replace_references([second])
    assert not q.has_cached(display_descriptor(base,first),window,3)
    assert q.has_cached(display_descriptor(base,second),window,3)
    assert len(w.view.layers.pixmap_cache)==1
