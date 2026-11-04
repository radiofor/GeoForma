"""Panel hovering and repeated status refreshes do not rebuild the widget tree."""
from collections import Counter
from PySide6.QtCore import QObject,QEvent,QPoint,QAbstractAnimation
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget
from geoforma.ui.button_feedback import PressFeedback
from test_workbench import workbench
from test_stable_panels import rectangles,settle


class PanelEvents(QObject):
    def __init__(self,window):super().__init__();self.window=window;self.events=Counter()
    def eventFilter(self,obj,event):
        kind=event.type()
        if isinstance(obj,PressFeedback) and kind in (QEvent.Type.Show,QEvent.Type.Hide):self.events['overlay_structure']+=1
        if kind in (QEvent.Type.LayoutRequest,QEvent.Type.StyleChange) and isinstance(obj,QWidget) and self.window.isAncestorOf(obj):self.events[kind.name]+=1
        return False


def test_hover_across_panels_reuses_overlays_without_layout_or_visibility_changes(workbench,hover_move):
    w,app,wait,errors=workbench;w.resize(1440,1000);w.view.setFocus();settle(app)
    controls=[w.single_polygon,w.smooth_enabled,w.auto_apply,w.apply_button,w.model_button,
              w.import_button,w.main_image_button,w.settings_button]
    overlays=[control._geoforma_feedback for control in controls];before=rectangles(w)
    spy=PanelEvents(w);app.installEventFilter(spy)
    try:
        for _ in range(3):
            for control in controls:
                for fraction in (.15,.45,.75):hover_move(control,QPoint(int(control.width()*fraction),control.height()//2))
        hover_move(w.view.viewport(),QPoint(10,10));settle(app)
        assert not spy.events and rectangles(w)==before
        assert all(control._geoforma_feedback is overlay for control,overlay in zip(controls,overlays))
        assert all(overlay.animation.state()==QAbstractAnimation.State.Stopped for overlay in overlays)
    finally:app.removeEventFilter(spy)
    assert not errors


def test_repeated_control_status_refreshes_do_not_restyle_or_relayout_panels(workbench):
    w,app,wait,errors=workbench;settle(app);before=rectangles(w);spy=PanelEvents(w);app.installEventFilter(spy)
    try:
        for _ in range(30):w.update_controls();app.processEvents()
        assert not spy.events and rectangles(w)==before
    finally:app.removeEventFilter(spy)
    assert not errors
