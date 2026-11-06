import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from geoforma.viewport import ImageView


def settle(app):
    for _ in range(12):app.processEvents()


@pytest.fixture
def view():
    app=QApplication.instance() or QApplication([])
    v=ImageView();v.resize(800,600);v.show();settle(app)
    yield v,app
    v.close();settle(app)


def bars(v):return v.horizontalScrollBar().isVisible(),v.verticalScrollBar().isVisible()


def test_empty_and_full_image_hide_both_bars_after_zoom(view):
    v,app=view;assert bars(v)==(False,False)
    v.set_image(1000,1000);settle(app);assert bars(v)==(False,False)
    v.zoom_at(QPoint(400,300),3);settle(app);assert bars(v)==(False,False)
    v.fit_image();settle(app)
    assert bars(v)==(False,False) and v.sceneRect()==v.raster_rect
    v.set_image(0,0);settle(app);assert bars(v)==(False,False)


@pytest.mark.parametrize('size', [(2000,200),(200,2000)])
def test_both_bars_remain_hidden_at_every_aspect_ratio(view,size):
    v,app=view;v.set_image(*size);settle(app)
    v.zoom_at(QPoint(400,300),2);settle(app)
    assert bars(v)==(False,False)
    assert v.horizontalScrollBarPolicy()==v.verticalScrollBarPolicy()==Qt.ScrollBarPolicy.ScrollBarAlwaysOff


def test_zoom_out_and_resize_keep_bars_hidden(view):
    v,app=view;v.set_image(1000,1000);settle(app)
    v.zoom_at(QPoint(400,300),2);settle(app)
    v.zoom_at(QPoint(400,300),.25);settle(app)
    assert bars(v)==(False,False)
    v.resize(180,160);settle(app);assert bars(v)==(False,False)
    v.resize(900,800);settle(app)
    v.fit_image();settle(app);assert bars(v)==(False,False)


def test_cursor_zoom_anchor_is_preserved_without_bars(view):
    v,app=view;v.set_image(2000,2000);settle(app)
    position=QPoint(360,230);before=v.mapToScene(position)
    v.zoom_at(position,2);settle(app)
    after=v.mapToScene(position)
    assert (after-before).manhattanLength()<4/v.transform().m11()


@pytest.mark.parametrize('button',[Qt.MouseButton.LeftButton,Qt.MouseButton.MiddleButton])
def test_mouse_pan_works_with_hidden_scrollbars(view,button):
    v,app=view;v.set_image(1000,1000);settle(app);v.zoom_at(QPoint(400,300),3);settle(app)
    v.set_mode('pan');start=QPoint(400,300);before=v.mapToScene(start)
    QTest.mousePress(v.viewport(),button,pos=start)
    QTest.mouseMove(v.viewport(),start+QPoint(70,45),delay=5)
    QTest.mouseRelease(v.viewport(),button,pos=start+QPoint(70,45));settle(app)
    assert (v.mapToScene(start)-before).manhattanLength()>5 and bars(v)==(False,False)


def test_navigation_restore_preserves_center_without_scrollbars(view):
    v,app=view;v.set_image(1600,1000);settle(app);v.zoom_at(QPoint(300,220),3);settle(app)
    before=v.capture_navigation();v.fit_image();v.restore_navigation(before);settle(app)
    after=v.capture_navigation()
    assert abs(after['scale']-before['scale'])<1e-9
    assert sum(abs(x-y) for x,y in zip(after['center'],before['center']))<4/after['scale']
    assert bars(v)==(False,False)
