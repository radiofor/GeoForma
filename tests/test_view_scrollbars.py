import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication
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
    v.zoom_at(QPoint(400,300),3);settle(app);assert bars(v)==(True,True)
    v.fit_image();settle(app)
    assert bars(v)==(False,False) and v.sceneRect()==v.raster_rect
    v.set_image(0,0);settle(app);assert bars(v)==(False,False)


@pytest.mark.parametrize('size,expected', [((2000,200),(True,False)),((200,2000),(False,True))])
def test_each_direction_is_independent(view,size,expected):
    v,app=view;v.set_image(*size);settle(app)
    v.zoom_at(QPoint(400,300),2);settle(app)
    assert bars(v)==expected
    assert not v.scrollbar_timer.isActive()


def test_zoom_out_hides_bars_and_resize_reevaluates(view):
    v,app=view;v.set_image(1000,1000);settle(app)
    v.zoom_at(QPoint(400,300),2);settle(app)
    v.zoom_at(QPoint(400,300),.25);settle(app)
    assert bars(v)==(False,False)
    v.resize(180,160);settle(app);assert bars(v)==(True,True)
    v.resize(900,800);settle(app)
    v.fit_image();settle(app);assert bars(v)==(False,False)


def test_cursor_zoom_anchor_is_preserved_when_bars_appear(view):
    v,app=view;v.set_image(2000,2000);settle(app)
    position=QPoint(360,230);before=v.mapToScene(position)
    v.zoom_at(position,2);settle(app)
    after=v.mapToScene(position)
    assert (after-before).manhattanLength()<4/v.transform().m11()
