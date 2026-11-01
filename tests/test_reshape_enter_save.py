import copy,time
import pytest
from PySide6.QtCore import Qt,QEvent
from PySide6.QtGui import QKeyEvent
from PySide6.QtTest import QTest
from shapely.geometry import shape
from test_reshape import workbench,raster_image,OUT


@pytest.mark.parametrize('key',[Qt.Key.Key_Return,Qt.Key.Key_Enter])
@pytest.mark.parametrize('finish',['button','right_click'])
def test_enter_saves_reshape_only_after_the_stroke_is_finished(workbench,key,finish):
    w,app,_=workbench;w.show();app.processEvents();before=copy.deepcopy(w.project['labels'])
    w.begin_reshape();w.reshape_session['stroke']=copy.deepcopy(OUT);w.view.set_reshape_stroke(OUT)
    QTest.keyClick(w.view.viewport(),key);assert w.reshape_session is not None and w.project['labels']==before
    w.update_controls()
    if finish=='button':w.reshape_preview_button.click()
    else:QTest.mouseClick(w.view.viewport(),Qt.MouseButton.RightButton)
    deadline=time.monotonic()+5
    while w.task:
        app.processEvents();QTest.qWait(2);assert time.monotonic()<deadline
    assert w.reshape_session is None and w.project['labels']==before
    assert w.confirm_button.isEnabled() and w.view.mode=='reshape'
    assert w.labels_table.item(0,2).text()=='未保存'
    QTest.keyClick(w.view.viewport(),key);app.processEvents()
    assert not w.draft and shape(w.project['labels'][0]['geometry']).area==124
    assert w.project['labels'][0]['editing_state']=='manual' and w.view.mode=='reshape'
    assert w.labels_table.item(0,2).text()=='已保存'
    history=len(w.label_undo)
    QTest.keyClick(w.view.viewport(),key);app.processEvents()
    assert len(w.label_undo)==history


def test_enter_repeat_does_not_save_and_pending_draft_cannot_be_saved(workbench):
    w,app,_=workbench;w.edit_selected(locate=False);before=copy.deepcopy(w.project['labels'])
    event=QKeyEvent(QEvent.Type.KeyPress,Qt.Key.Key_Return,Qt.KeyboardModifier.NoModifier,'',True,1)
    w.view.keyPressEvent(event)
    assert w.draft and w.project['labels']==before and not w.label_undo
    w.draft['pending']=True;w.update_controls()
    QTest.keyClick(w.view.viewport(),Qt.Key.Key_Return)
    assert w.draft['pending'] and w.project['labels']==before and not w.label_undo
