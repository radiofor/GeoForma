import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import numpy as np
import pytest
from types import SimpleNamespace
from PySide6.QtWidgets import QApplication
from geoforma.domain import prompt_window
from geoforma.window import MainWindow
from geoforma.inference.engine import ModelEngine

def test_group_and_box_use_prepared_tile_and_large_target_expands():
    assert prompt_window([[200,200,1],[300,300,0]])==(-128,-128,1024,1024)
    assert prompt_window([],[200,200,300,300])==(-128,-128,1024,1024)
    assert prompt_window([],[0,0,2000,2000])[2]>1024

def test_window_input_reuses_recipe_key_but_invalidates_changed_key(monkeypatch):
    import geoforma.inference.engine as module
    reads=[];engine=ModelEngine();engine.backend=SimpleNamespace(key=lambda image,window:image['key'])
    monkeypatch.setattr(module,'read_rgb',lambda image,window:(reads.append(image['key']) or np.zeros((2,2,3),np.uint8),np.ones((2,2),bool)))
    engine.window_input({'key':'a'},[0,0,2,2]);engine.window_input({'key':'a'},[0,0,2,2]);engine.window_input({'key':'b'},[0,0,2,2])
    assert reads==['a','b']

def test_preview_cannot_encode_a_missing_window():
    engine=ModelEngine();engine.prepare_backend=lambda *a:None
    engine.backend=SimpleNamespace(restore=lambda *a:False)
    assert engine.preview({}, {}, {'window':[0,0,1024,1024]},None) is None

def test_simplified_controls_and_draft_do_not_block_candidates():
    app=QApplication.instance() or QApplication([]);w=MainWindow(auto_prepare=False);w.autosave=lambda:None
    w.image={'id':'test','ready':True,'width':1000,'height':1000,'model_recipe':None,'display_recipe':None};w.draft={'points':[[10,10,1]],'pending':True}
    w.update_controls();assert not hasattr(w,'auto_button') and not hasattr(w,'choice_row')
    assert not hasattr(w,'options_menu')
    assert not hasattr(w,'hover_preview') and not hasattr(w,'draft_info')
    w.invalidate_preview();assert w.view.preview_item is None
    w.dirty=False;w.close();app.processEvents()


@pytest.mark.parametrize('automatic',[False,True])
def test_drag_box_only_updates_rectangle_and_predicts_after_release(automatic):
    from PySide6.QtCore import Qt,QPointF
    from PySide6.QtTest import QTest
    app=QApplication.instance() or QApplication([]);w=MainWindow(auto_prepare=False);w.autosave=lambda:None
    w.image={'id':'test','ready':True,'width':1000,'height':1000,'model_recipe':None,'display_recipe':None}
    w.view.set_image(1000,1000);w.render_timer.stop();w.show();app.processEvents()
    w.view.fit_image();w.render_timer.stop();w.set_tool('box');w.auto_apply.setChecked(automatic)
    previews=[];predictions=[];w.service.preview=lambda *args:previews.append(args)
    w.predict=lambda:predictions.append(w.draft['box'])
    start=w.view.mapFromScene(QPointF(100,100));end=w.view.mapFromScene(QPointF(300,300))
    QTest.mousePress(w.view.viewport(),Qt.MouseButton.LeftButton,pos=start)
    QTest.mouseMove(w.view.viewport(),end);QTest.qWait(100)
    assert w.view.rubber is not None and w.view.rubber.rect().width()>2
    assert not previews and not predictions
    assert w.view.preview_item is None and not w.draft.get('box')
    QTest.mouseRelease(w.view.viewport(),Qt.MouseButton.LeftButton,pos=end);QTest.qWait(100)
    assert w.view.rubber is None and w.draft.get('box')
    assert len(predictions)==int(automatic) and not previews
    w.image=None;w.dirty=False;w.close();app.processEvents()

def test_hover_events_never_schedule_inference_or_change_draft():
    import copy
    from PySide6.QtTest import QTest
    app=QApplication.instance() or QApplication([]);w=MainWindow(auto_prepare=False);w.autosave=lambda:None
    w.image={'id':'test','ready':True,'width':1000,'height':1000,'model_recipe':None,'display_recipe':None}
    w.view.set_image(1000,1000);w.render_timer.stop();w.draft={'points':[[120,120,1]],'pending':True}
    original=copy.deepcopy(w.draft);calls=[]
    w.service.preview=lambda *args:calls.append(args)
    assert not hasattr(w,'hover_preview') and not hasattr(w,'draft_info')
    from PySide6.QtCore import QPointF
    w.show();app.processEvents();w.set_tool('positive');w.render_timer.stop()
    for x in range(150,180):QTest.mouseMove(w.view.viewport(),w.view.mapFromScene(QPointF(x,150)))
    QTest.qWait(100)
    assert not calls and w.task is None and w.view.preview_item is None and w.draft==original
    w.image=None;w.dirty=False;w.close();app.processEvents()
