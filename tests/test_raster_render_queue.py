import os,threading,time
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import numpy as np
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication
from geoforma.rendering.raster_queue import RasterRenderQueue


def wait(app,condition):
    end=time.monotonic()+4
    while not condition() and time.monotonic()<end:app.processEvents();time.sleep(.002)
    assert condition()


def image(identifier='image'):
    return dict(id=identifier,path=identifier+'.tif',width=1000,height=1000,display_recipe={'bands':[1,2,3]},working_draft={'large':'excluded'})


def test_latest_view_only_cache_reuse_and_window_memory_bound():
    app=QApplication.instance() or QApplication([]);pool=QThreadPool();pool.setMaxThreadCount(1)
    release=threading.Event();started=threading.Event();reads=[];published=[]
    def reader(im,window,recipe,size):
        assert 'working_draft' not in im;reads.append(window)
        if len(reads)==1:started.set();release.wait(3)
        return np.zeros((2,2,3),np.uint8),np.ones((2,2),bool)
    queue=RasterRenderQueue(pool,reader,max_bytes=32);queue.rendered.connect(lambda value,window,overview:published.append(window))
    a,b,c=(0,0,100,100),(100,0,100,100),(200,0,100,100)
    queue.request(image(),1,a,100);wait(app,started.is_set)
    queue.viewport_changed();queue.request(image(),1,b,100)
    queue.viewport_changed();queue.request(image(),1,c,100);release.set()
    wait(app,lambda:queue.task is None and len(reads)==2)
    assert reads==[a,c] and published==[c] and queue.discarded==1
    queue.viewport_changed();queue.request(image(),1,a,100)
    assert published[-1]==a and len(reads)==2 and queue.hits==1
    queue.request(image(),1,a,100);assert len(reads)==2
    queue.request(image(),1,b,100);wait(app,lambda:queue.task is None)
    assert queue.cache_bytes<=32 and len(queue.cache)<=2
    queue.close();pool.waitForDone()


def test_switch_image_discards_even_old_overview():
    app=QApplication.instance() or QApplication([]);pool=QThreadPool();pool.setMaxThreadCount(1)
    release=threading.Event();started=threading.Event();published=[]
    def reader(im,*args):
        if im['id']=='old':started.set();release.wait(3)
        return np.full((2,2,3),1 if im['id']=='old' else 2,np.uint8),np.ones((2,2),bool)
    queue=RasterRenderQueue(pool,reader);queue.rendered.connect(lambda value,*args:published.append(int(value[0][0,0,0])))
    queue.request(image('old'),1,(0,0,1000,1000),100,True);wait(app,started.is_set)
    queue.reset(2);queue.request(image('new'),2,(0,0,1000,1000),100,True);release.set()
    wait(app,lambda:queue.task is None)
    assert published==[2] and queue.discarded==1
    queue.close();pool.waitForDone()


def test_image_switch_keeps_overview_and_latest_detail_while_old_read_finishes():
    app=QApplication.instance() or QApplication([]);pool=QThreadPool();pool.setMaxThreadCount(1)
    release=threading.Event();started=threading.Event();published=[];reads=[]
    def reader(im,window,*args):
        reads.append((im['id'],tuple(window)))
        if im['id']=='old':started.set();release.wait(3)
        return np.zeros((2,2,3),np.uint8),np.ones((2,2),bool)
    queue=RasterRenderQueue(pool,reader)
    queue.rendered.connect(lambda value,window,overview:published.append((tuple(window),overview)))
    try:
        queue.request(image('old'),1,(0,0,1000,1000),100,True);wait(app,started.is_set)
        queue.reset(2);queue.request(image('new'),2,(0,0,1000,1000),100,True)
        queue.viewport_changed();queue.request(image('new'),2,(100,100,200,200),100)
        queue.viewport_changed();queue.request(image('new'),2,(200,200,200,200),100)
        release.set();wait(app,lambda:queue.task is None and len(published)==2)
        assert published==[((0,0,1000,1000),True),((200,200,200,200),False)]
        assert len(reads)==3
    finally:release.set();queue.close();pool.waitForDone()


def test_return_to_displayed_view_drops_obsolete_pending_detail():
    app=QApplication.instance() or QApplication([]);pool=QThreadPool();pool.setMaxThreadCount(1)
    release=threading.Event();started=threading.Event();reads=[];published=[]
    a,b,c=(0,0,100,100),(100,0,100,100),(200,0,100,100)
    def reader(im,window,*args):
        reads.append(tuple(window))
        if tuple(window)==b:started.set();release.wait(3)
        return np.zeros((2,2,3),np.uint8),np.ones((2,2),bool)
    queue=RasterRenderQueue(pool,reader);queue.rendered.connect(lambda value,window,overview:published.append(tuple(window)))
    try:
        queue.request(image(),1,a,100);wait(app,lambda:queue.task is None)
        queue.viewport_changed();queue.request(image(),1,b,100);wait(app,started.is_set)
        queue.viewport_changed();queue.request(image(),1,c,100)
        queue.viewport_changed();queue.request(image(),1,a,100);release.set()
        wait(app,lambda:queue.task is None)
        assert reads==[a,b] and published==[a]
    finally:release.set();queue.close();pool.waitForDone()


def test_raster_item_reused_when_display_pixels_change():
    from geoforma.viewport import ImageView
    app=QApplication.instance() or QApplication([]);view=ImageView();view.set_image(1000,1000)
    rgb=np.zeros((10,10,3),np.uint8);valid=np.ones((10,10),bool)
    view.show_raster(rgb,valid,(0,0,1000,1000),True);overview=view.base_item
    view.show_raster(rgb+100,valid,(0,0,1000,1000),True);assert view.base_item is overview
    view.show_raster(rgb,valid,(0,0,200,200));detail=view.detail_item
    view.show_raster(rgb,valid,(100,100,200,200));assert view.detail_item is detail and detail.pos().x()==100
    view.show_preview(valid,(0,0,200,200));preview=view.preview_item
    view.show_preview(valid,(100,100,200,200));assert view.preview_item is preview
    view.set_overlay_visibility(False);assert not preview.isVisible()
    view.close()


def test_detail_nodata_does_not_reveal_coarser_overview():
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QColor,QImage,QPainter
    from geoforma.viewport import ImageView
    app=QApplication.instance() or QApplication([]);view=ImageView();view.set_image(40,40)
    overview=np.full((10,10,3),200,np.uint8)
    view.show_raster(overview,np.ones((10,10),bool),(0,0,40,40),True)
    detail=np.full((20,20,3),100,np.uint8);valid=np.ones((20,20),bool);valid[6:14,6:14]=False
    view.show_raster(detail,valid,(10,10,20,20))
    def render():
        canvas=QImage(40,40,QImage.Format.Format_ARGB32);canvas.fill(QColor(17,31,47))
        painter=QPainter(canvas);view.scene().render(painter,QRectF(0,0,40,40),QRectF(0,0,40,40));painter.end()
        return canvas
    canvas=render()
    assert canvas.pixelColor(20,20)==QColor(17,31,47)
    assert canvas.pixelColor(12,12)==QColor(100,100,100)
    assert canvas.pixelColor(4,4)==QColor(200,200,200)
    view.layers.clear_detail();assert render().pixelColor(20,20)==QColor(200,200,200)
    view.scene().clear();view.layers.reset();view.close();view.deleteLater();app.processEvents()


def test_old_project_result_cannot_repopulate_a_cleared_display_cache():
    app=QApplication.instance() or QApplication([]);pool=QThreadPool();pool.setMaxThreadCount(1)
    release=threading.Event();started=threading.Event()
    def reader(*args):
        started.set();assert release.wait(3)
        return np.zeros((2,2,3),np.uint8),np.ones((2,2),bool)
    queue=RasterRenderQueue(pool,reader)
    try:
        queue.request(image('old'),1,(0,0,1000,1000),100,True);wait(app,started.is_set)
        queue.reset(2,clear_cache=True);release.set();wait(app,lambda:queue.task is None)
        assert not queue.cache and queue.cache_bytes==0 and queue.discarded==1
    finally:release.set();queue.close();pool.waitForDone()
