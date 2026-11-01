"""Cached reveals keep exact endpoint frames and move text without stretching."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtCore import QRect,QRectF
from PySide6.QtGui import QColor,QPainter,QPixmap
from PySide6.QtWidgets import QApplication
from geoforma.ui.sidebar_transition import SidebarTransition


@pytest.fixture(scope='module')
def app():return QApplication.instance() or QApplication([])


def snapshot(height,dpr):
    result=QPixmap(round(400*dpr),round(600*dpr));result.setDevicePixelRatio(dpr);result.fill(QColor('white'))
    painter=QPainter(result);painter.fillRect(QRectF(10,20,280,560),QColor('#f6f9fa'))
    painter.fillRect(QRectF(10,112,280,height+210),QColor('#ccaabb'))
    painter.fillRect(QRectF(22,150,256,height),QColor('white'))
    painter.fillRect(QRectF(22,150,256,1),QColor('#3377aa'))
    painter.fillRect(QRectF(22,150+height-1,256,1),QColor('#3377aa'))
    painter.fillRect(QRectF(40,170,20,10),QColor('#223344'))
    painter.fillRect(QRectF(40,150+height+10,20,10),QColor('#7744bb'))
    painter.end();return result


@pytest.mark.parametrize('dpr',[1.,1.5,2.])
@pytest.mark.parametrize('heights',[(72,160),(160,72)])
def test_reveal_has_exact_endpoints_and_translates_tail_without_resizing_text(app,dpr,heights):
    before,after=heights;viewport=QRectF(10,20,280,560)
    old,new=snapshot(before,dpr),snapshot(after,dpr)
    transition=SidebarTransition.create((QRectF(22,150,256,before),viewport),(QRectF(22,150,256,after),viewport))
    assert transition is not None
    for blend in (1.,.5,0.):
        result=QPixmap(old.size());result.setDevicePixelRatio(dpr);result.fill(QColor('white'))
        painter=QPainter(result);painter.drawPixmap(QRect(0,0,400,600),new)
        painter.setOpacity(blend);painter.drawPixmap(QRect(0,0,400,600),old)
        transition.paint(painter,QRect(0,0,400,600),old,new,blend);painter.end();pixels=result.toImage()
        if blend==1.:assert pixels==old.toImage()
        elif blend==0.:assert pixels==new.toImage()
        else:
            assert pixels.pixelColor(round(45*dpr),round(175*dpr))==QColor('#223344')
            y=150+(before+after)/2+10
            assert pixels.pixelColor(round(45*dpr),round((y+3)*dpr))==QColor('#7744bb')
            assert pixels.pixelColor(round(45*dpr),round((y-2)*dpr))!=QColor('#7744bb')
            assert pixels.pixelColor(round(45*dpr),round((y+12)*dpr))!=QColor('#7744bb')
