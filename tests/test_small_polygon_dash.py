"""Small outlines retain distinct dashes after antialiased rendering."""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor,QImage,QPainter,QPainterPath,QPen
from PySide6.QtWidgets import QStyleOptionGraphicsItem

from geoforma.rendering.label_item import LabelItem


@pytest.mark.parametrize('scale',[.5,1.,2.])
@pytest.mark.parametrize('selected',[False,True])
def test_small_polygon_keeps_white_gaps_between_colored_dashes(scale,selected):
    path=QPainterPath();path.addRect(12,12,18,12)
    image=QImage(100,80,QImage.Format.Format_ARGB32);image.fill(Qt.GlobalColor.transparent)
    item=LabelItem();item.highlighted=selected;item.setPath(path);item.setPen(QPen(QColor('red')))
    painter=QPainter(image);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.translate(5,5);painter.scale(scale,scale)
    item.paint(painter,QStyleOptionGraphicsItem());painter.end()
    y=round(5+12*scale)
    colors=[image.pixelColor(x,y) for x in range(round(5+12*scale)+2,round(5+30*scale)-2)]
    assert any(color.red()>220 and color.green()<150 for color in colors)
    assert any(color.red()>245 and color.green()>240 and color.blue()>240 for color in colors)


def test_small_interior_ring_keeps_a_visible_gap():
    # A small hole shares one retained item with a much larger outer ring.
    path=QPainterPath();path.addRect(5,5,65,65);path.addRect(25,25,9,8)
    image=QImage(90,90,QImage.Format.Format_ARGB32);image.fill(Qt.GlobalColor.transparent)
    item=LabelItem();item.setPath(path);item.setPen(QPen(QColor('red')))
    painter=QPainter(image);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    item.paint(painter,QStyleOptionGraphicsItem());painter.end()
    colors=[image.pixelColor(x,25) for x in range(26,34)]
    assert any(color.red()>220 and color.green()<150 for color in colors)
    assert any(color.red()>245 and color.green()>240 and color.blue()>240 for color in colors)
