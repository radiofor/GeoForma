"""The image list stays scrollable while the reshape tool is active."""
import copy

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from test_reshape import OUT, workbench, raster_image
from test_reshape_auto import wait
from test_smoothing import settled


def check_image_scrolling(w,app):
    bar=w.images.verticalScrollBar()
    assert w.images.isEnabled() and bar.isVisible() and bar.isEnabled()
    bar.setValue(0)
    pos=QPoint(20,20);global_pos=w.images.viewport().mapToGlobal(pos)
    wheel=QWheelEvent(QPointF(pos),QPointF(global_pos),QPoint(),QPoint(0,-120),
                      Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier,
                      Qt.ScrollPhase.NoScrollPhase,False)
    QApplication.sendEvent(w.images.viewport(),wheel);app.processEvents()
    assert bar.value()>0


def test_reshape_keeps_image_list_scrollbar_enabled(workbench):
    w,app,_=workbench
    source=w.image
    images=[source]
    for index in range(35):
        image=copy.deepcopy(source)
        image.update(id=f'image-{index}',name=f'image-{index}.tif')
        images.append(image)
    w.project['images']=images
    w.refresh_images();w.resize(1200,800);w.show();app.processEvents();settled(w,app)
    bar=w.images.verticalScrollBar()
    assert bar.maximum()>0 and bar.isVisible() and bar.isEnabled()
    assert w.view.horizontalScrollBarPolicy()==Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert w.view.verticalScrollBarPolicy()==Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    w.begin_reshape(auto=True);app.processEvents()
    check_image_scrolling(w,app)
    for x,y in OUT:w.add_reshape_point(x,y)
    check_image_scrolling(w,app)
    w.finish_reshape();wait(w,app);settled(w,app)
    assert w.reshape_session is None
    check_image_scrolling(w,app)


def test_clicking_another_image_leaves_unfinished_reshape(workbench):
    w,app,_=workbench
    other=copy.deepcopy(w.image);other.update(id='other-image',name='other.tif')
    w.project['images']=[w.image,other]
    w.refresh_images();w.resize(1200,800);w.show();app.processEvents();settled(w,app)
    w.begin_reshape(auto=True)
    for x,y in OUT[:2]:w.add_reshape_point(x,y)
    assert w.reshape_session and w.reshape_session['stroke']
    row=w.images.item(1);w.images.scrollToItem(row);app.processEvents()
    QTest.mouseClick(w.images.viewport(),Qt.MouseButton.LeftButton,
                     pos=w.images.visualItemRect(row).center())
    app.processEvents()
    assert w.image is other and w.reshape_session is None
    assert w.images.isEnabled()


def test_computing_reshape_keeps_list_scrollable_but_blocks_switch_and_review(workbench,monkeypatch):
    import threading,time
    from geoforma import reshape
    w,app,_=workbench;source=w.image;images=[source]
    for index in range(35):
        image=copy.deepcopy(source);image.update(id=f'pending-{index}',name=f'pending-{index}.tif');images.append(image)
    w.project['images']=images;w.refresh_images();w.resize(1200,800);w.show();app.processEvents();settled(w,app)
    started=threading.Event();release=threading.Event();real=reshape.reshape_geometry
    def delayed(*args,**kwargs):
        started.set()
        while not release.wait(.005):args[7].check()
        return real(*args,**kwargs)
    monkeypatch.setattr(reshape,'reshape_geometry',delayed)
    try:
        w.begin_reshape(auto=True)
        for point in OUT:w.add_reshape_point(*point)
        w.finish_reshape();deadline=time.monotonic()+8
        while not started.is_set():app.processEvents();QTest.qWait(2);assert time.monotonic()<deadline
        assert w.task_kind=='reshape';check_image_scrolling(w,app)
        row=w.images.item(1);w.images.scrollToItem(row);app.processEvents()
        rect=w.images.visualItemRect(row)
        QTest.mouseClick(w.images.viewport(),Qt.MouseButton.LeftButton,pos=rect.center());app.processEvents()
        assert w.image is source and w.images.currentRow()==0
        w.images.scrollToItem(row);app.processEvents();rect=w.images.visualItemRect(row)
        point=w.images.itemDelegate().review_rect(rect).center()
        QTest.mouseClick(w.images.viewport(),Qt.MouseButton.LeftButton,pos=point);app.processEvents()
        assert not images[1].get('review_complete',False) and w.image is source
    finally:release.set()
    wait(w,app);assert w.reshape_session is None
