"""Hover help stays hidden for toolbar icons, ordinary controls and item views."""
import pytest
from PySide6.QtCore import QPoint,QEvent
from PySide6.QtGui import QHelpEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QToolTip
from test_workbench import workbench


def help_event(widget):
    pos=widget.rect().center()
    QApplication.sendEvent(widget,QHelpEvent(QEvent.Type.ToolTip,pos,widget.mapToGlobal(pos)))


def test_other_controls_and_item_views_never_show_hover_help(workbench):
    w,app,wait,errors=workbench
    controls=[w.single_polygon,w.smooth_value,w.confirm_button,w.export_crs_input,
              w.project_title,w.main_image_button,w.images.viewport(),w.labels_table.viewport(),w.settings_menu]
    for control in controls:
        control.setToolTip('不显示的悬浮提示');help_event(control)
        assert not QToolTip.isVisible()


@pytest.mark.parametrize('disabled',[False,True])
def test_toolbar_icons_never_show_help_even_after_stationary_hover(workbench,disabled):
    w,app,wait,errors=workbench;button=w.settings_button;button.setEnabled(not disabled)
    QTest.mouseMove(button,button.rect().center());help_event(button)
    QTest.qWait(1000);assert not QToolTip.isVisible()
    eye=w.visibility_toolbar.widgetForAction(w.raw_view_action)
    QTest.mouseMove(eye,eye.rect().center());help_event(eye)
    QTest.qWait(1000);assert not QToolTip.isVisible()
    QTest.mouseMove(w.view.viewport(),QPoint(10,10))
