"""Raster boundaries stay seamless at fractional view transforms."""
import pytest
from PySide6.QtCore import Qt,QRectF
from PySide6.QtGui import QColor,QImage,QPainter,QPixmap,QTransform
from PySide6.QtWidgets import QApplication,QGraphicsScene
from geoforma.rendering.scene_layers import RasterOverviewItem,RasterDetailItem

_APP=None


@pytest.mark.parametrize('scale',[.51,.73,1.0,1.17,1.37,1.91,2.5,4.2])
@pytest.mark.parametrize('offset',[(25.37,25.13),(25.13,25.79)])
def test_fractional_zoom_has_no_dark_detail_seam_and_preserves_nodata(scale,offset):
    global _APP
    _APP=QApplication.instance() or QApplication([])
    scene=QGraphicsScene();scene.setBackgroundBrush(QColor('#101010'))
    overview=QImage(100,100,QImage.Format.Format_ARGB32);overview.fill(QColor('#cccccc'))
    base=RasterOverviewItem(QPixmap.fromImage(overview));scene.addItem(base)
    base.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
    image=QImage(35,37,QImage.Format.Format_ARGB32);image.fill(QColor('#cccccc'))
    for y in range(12,22):
        for x in range(12,22):image.setPixelColor(x,y,QColor(0,0,0,0))
    detail=RasterDetailItem(QPixmap.fromImage(image));scene.addItem(detail)
    detail.setPos(23,24);detail.setTransform(QTransform.fromScale(33/35,38/37));detail.setZValue(1)
    detail.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
    base.excluded=base.mapFromItem(detail,detail.boundingRect()).boundingRect()
    output=QImage(520,520,QImage.Format.Format_RGB32);output.fill(QColor('#101010'))
    painter=QPainter(output);painter.setRenderHint(QPainter.RenderHint.Antialiasing,True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform,True)
    painter.translate(*offset);painter.scale(scale,scale)
    scene.render(painter,QRectF(0,0,100,100),QRectF(0,0,100,100));painter.end()
    # Boundary pixels are fully opaque and should not reveal the dark canvas.
    for y in range(int(offset[1]+scale*25)+1,int(offset[1]+scale*35)-1):
        for x in range(int(offset[0]+scale*20)+1,int(offset[0]+scale*60)-1):
            assert output.pixelColor(x,y).red()>=180,(scale,offset,x,y)
    # A hole inside the detail remains transparent rather than exposing overview.
    x=round(offset[0]+scale*(23+17*33/35));y=round(offset[1]+scale*(24+17*38/37))
    assert output.pixelColor(x,y).red()<=25


@pytest.mark.parametrize('is_reference',[False,True])
def test_real_view_zoom_and_detail_move_keep_nodata_correct(is_reference):
    import numpy as np
    from PySide6.QtTest import QTest
    from geoforma.viewport import ImageView
    global _APP
    _APP=QApplication.instance() or QApplication([])
    view=ImageView();view.resize(320,320);view.show();view.set_image(100,100)
    rgb=np.full((100,100,3),204,dtype=np.uint8);valid=np.ones((100,100),dtype=bool)
    source=('reference','recipe') if is_reference else None
    view.show_raster(rgb,valid,[0,0,100,100],True,source)
    tile=np.full((37,35,3),204,dtype=np.uint8);mask=np.ones((37,35),dtype=bool)
    mask[12:22,0:10]=False;mask[28,20]=False
    view.resetTransform();view.scale(4.2,4.2);view.translate(.13,.37);view.centerOn(50,50)
    try:
        for left in (23,26,23):
            view.show_raster(tile,mask,[left,24,33,38],False,source)
            _APP.processEvents();QTest.qWait(5)
            snapshot=view.viewport().grab().toImage()
            def sample(x,y):
                p=view.mapFromScene(x,y);return snapshot.pixelColor(p.x(),p.y()).red()
            assert sample(left-1,24+17*38/37)>=180
            assert sample(left+3*33/35,24+17*38/37)<100
            assert sample(left+20.5*33/35,24+28.5*38/37)<100
            y=24+5*38/37;p0=view.mapFromScene(left-2,y);p1=view.mapFromScene(left+35,y)
            assert min(snapshot.pixelColor(x,p0.y()).red() for x in range(p0.x(),p1.x()))>=180
    finally:view.close();view.deleteLater();_APP.processEvents()


def test_raster_alpha_mask_does_not_make_selection_shape_complex():
    import numpy as np
    from shapely.geometry import box,mapping
    from PySide6.QtWidgets import QGraphicsPixmapItem
    from geoforma.viewport import ImageView
    global _APP
    _APP=QApplication.instance() or QApplication([])
    view=ImageView();view.resize(320,320);view.show();view.set_image(100,100)
    rgb=np.full((100,100,3),204,dtype=np.uint8)
    valid=np.indices((100,100)).sum(axis=0)%2==0
    try:
        view.show_raster(rgb,valid,[0,0,100,100],True)
        view.show_raster(rgb,valid,[0,0,100,100],False)
        for item in (view.layers.base_item,view.layers.detail_item):
            assert item.shapeMode()==QGraphicsPixmapItem.ShapeMode.BoundingRectShape
            assert item.shape().elementCount()==5
        view.overlays([{'id':'label','status':'confirmed','geometry':mapping(box(20,20,40,40))}])
        _APP.processEvents()
        assert view.hit_label(view.mapFromScene(30,30))=='label'
    finally:view.close();view.deleteLater();_APP.processEvents()
