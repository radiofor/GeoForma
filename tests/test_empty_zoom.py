import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QPoint,QPointF,Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication
from geoforma.window import MainWindow


def test_empty_view_rejects_zoom_and_recovers_after_import():
    app=QApplication.instance() or QApplication([])
    w=MainWindow(auto_prepare=False);w.autosave=lambda:None
    assert not w.fit_action.isEnabled() and not w.native_zoom_action.isEnabled()
    before=w.view.transform();scene=w.view.sceneRect()
    w.view.zoom_at(QPoint(50,50),1.25)
    event=QWheelEvent(QPointF(50,50),QPointF(50,50),QPoint(),QPoint(0,120),Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier,Qt.ScrollPhase.NoScrollPhase,False)
    w.view.wheelEvent(event);w.zoom_native()
    assert w.view.transform()==before and w.view.sceneRect()==scene
    w.image={'id':'image','width':1000,'height':1000,'ready':False,'model_recipe':None}
    w.view.set_image(1000,1000);w.update_controls()
    assert w.fit_action.isEnabled() and w.native_zoom_action.isEnabled()
    scale=w.view.transform().m11();w.view.zoom_at(QPoint(50,50),1.25)
    assert w.view.transform().m11()>scale
    w.image=None;w.view.set_image(0,0);w.update_controls()
    assert w.view.transform().isIdentity() and not w.native_zoom_action.isEnabled()
    w.dirty=False;w.close();app.processEvents()
