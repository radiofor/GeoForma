import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import copy
from types import SimpleNamespace
import numpy as np
import pytest
from PySide6.QtCore import Qt,QPointF,QPoint
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from shapely.geometry import box,mapping
from geoforma.window import MainWindow


@pytest.fixture
def window():
    app=QApplication.instance() or QApplication([]);w=MainWindow();w.autosave=lambda:None
    w.auto_apply.setChecked(False)
    w.image={'id':'image','width':1000,'height':1000,'ready':True,'model_recipe':None,'display_recipe':None};w.view.set_image(1000,1000);w.show();app.processEvents();w.render_timer.stop()
    calls=[]
    def predict(image,config,request,task):
        calls.append(copy.deepcopy(request));return {'window':list(request['window']),'cache_hit':True,'device':'cpu','key':'test',
            'choices':[{'geometry':mapping(box(100,100,200+len(request['points']),200)),'score':.9,'edge':False,'logits':np.zeros((1,256,256),np.float32)}]}
    w.service.predict=predict
    w.run=lambda title,fn,callback,**kwargs:callback(fn(None))
    yield w,calls,app
    w.dirty=False;w.render_timer.stop();w.close();app.processEvents()


def test_deferred_apply_and_undo_after_apply(window):
    w,calls,_=window
    w.add_point(110,120,1);w.add_point(140,150,1);w.add_point(90,90,0)
    assert not calls and len(w.draft['points'])==3
    w.undo_prompt();assert len(w.draft['points'])==2 and not calls
    w.predict();assert len(calls)==1;applied=copy.deepcopy(w.draft['geometry'])
    w.undo_prompt();assert len(w.draft['points'])==1 and len(calls)==1 and w.draft['geometry']==applied
    assert w.draft['pending'] and not w.confirm_button.isEnabled()
    w.confirm();assert not w.project['labels']
    w.predict();assert len(calls)==2 and len(calls[-1]['points'])==1 and calls[-1]['logits'] is None and calls[-1]['seed'] is None
    w.redo_prompt();assert len(w.draft['points'])==2 and len(calls)==2
    w.selected_points={0};w.delete_points();assert len(w.draft['points'])==1 and len(calls)==2
    w.predict();assert calls[-1]['points']==[[140,150,1]]


def test_undo_last_point_requires_apply_to_clear_result(window):
    w,calls,_=window;w.add_point(120,120,1);w.predict();geometry=copy.deepcopy(w.draft['geometry'])
    w.undo_prompt();assert w.draft['points']==[] and w.draft['geometry']==geometry and len(calls)==1
    assert w.apply_button.isEnabled();w.predict();assert not w.draft.get('geometry') and len(calls)==1


def test_box_changes_and_expansion_are_staged(window):
    w,calls,_=window;w.add_box([120,120,200,200]);assert not calls;w.predict();assert len(calls)==1
    old=copy.deepcopy(w.draft['geometry']);w.stage_expand();assert len(calls)==1 and w.draft['pending'] and w.draft['window'][2]==2048
    w.predict();assert len(calls)==2;w.clear_box();assert len(calls)==2 and not w.draft['box']
    w.undo_prompt();assert w.draft['box']==[120,120,200,200] and len(calls)==2


def test_selecting_missing_model_starts_preparation_instead_of_warning(window,monkeypatch,tmp_path):
    w,_,_=window;calls=[]
    import PySide6.QtWidgets as ui
    class Dialog(ui.QDialog):
        def __init__(self,config,parent):super().__init__(parent)
        def exec(self):return True
        def value(self):return dict(w.project['model'],backend='sam',variant='vit_l',checkpoint=str(tmp_path/'not_downloaded.pth'))
    monkeypatch.setattr('geoforma.controllers.models.ModelDialog',Dialog)
    w.service.prepare_model=lambda config,task:(calls.append(config) or {'checkpoint':str(tmp_path/'official.pth'),'device':'cpu'})
    monkeypatch.setattr(ui.QMessageBox,'warning',lambda *a:pytest.fail('Missing weight must not require a manual file selection'))
    w.configure_model();assert len(calls)==1 and calls[0]['variant']=='vit_l'
    assert w.project['model']['checkpoint']==str(tmp_path/'official.pth')


def click(w,scene,modifiers=Qt.KeyboardModifier.NoModifier):
    QTest.mouseClick(w.view.viewport(),Qt.MouseButton.LeftButton,modifiers,w.view.mapFromScene(QPointF(*scene)))


def drag(w,start,end):
    a=w.view.mapFromScene(QPointF(*start));b=w.view.mapFromScene(QPointF(*end))
    QTest.mousePress(w.view.viewport(),Qt.MouseButton.LeftButton,pos=a);QTest.mouseMove(w.view.viewport(),b,20);QTest.mouseRelease(w.view.viewport(),Qt.MouseButton.LeftButton,pos=b)


def test_points_click_rectangle_delete_undo(window):
    w,calls,app=window
    for x,y,label in [(250,250,1),(400,400,0),(700,700,1)]:w.add_point(x,y,label)
    w.view.set_mode('select_points');click(w,(250,250));assert w.selected_points=={0}
    click(w,(400,400),Qt.KeyboardModifier.ControlModifier);assert w.selected_points=={0,1}
    click(w,(250,250),Qt.KeyboardModifier.ControlModifier);assert w.selected_points=={1}
    drag(w,(200,200),(500,500));assert w.selected_points=={0,1}
    w.view.setFocus();QTest.keyClick(w.view,Qt.Key.Key_Delete);app.processEvents()
    assert w.draft['points']==[[700,700,1]] and not calls
    QTest.keyClick(w.view,Qt.Key.Key_Z,Qt.KeyboardModifier.ControlModifier);assert len(w.draft['points'])==3 and not calls
    QTest.keyClick(w.view,Qt.Key.Key_Z,Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.ShiftModifier)
    assert w.draft['points']==[[700,700,1]] and not calls


def test_label_multi_selection_delete_atomic_undo(window):
    w,_,app=window
    w.project['labels']=[{'id':str(i),'image_id':'image','status':'confirmed','class_id':1,'geometry':mapping(box(x,200,x+80,280))} for i,x in enumerate([200,400,700])]
    original=copy.deepcopy(w.project['labels']);w.refresh_labels();w.view.set_mode('select')
    click(w,(230,230));assert w.selected_ids=={'0'}
    click(w,(430,230),Qt.KeyboardModifier.ControlModifier);assert w.selected_ids=={'0','1'}
    drag(w,(180,180),(500,300));assert w.selected_ids=={'0','1'}
    w.view.setFocus();QTest.keyClick(w.view,Qt.Key.Key_Delete);app.processEvents();assert [l['id'] for l in w.project['labels']]==['2']
    QTest.keyClick(w.view,Qt.Key.Key_Z,Qt.KeyboardModifier.ControlModifier);assert w.project['labels']==original


@pytest.mark.parametrize('point',[(25,30),(210,160),(500,300)])
def test_wheel_keeps_cursor_scene_position(window,point):
    w,_,app=window;position=QPoint(*point)
    for delta in [120,120,-120,-120,-120,120]:
        before=w.view.mapToScene(position)
        event=QWheelEvent(QPointF(position),QPointF(w.view.viewport().mapToGlobal(position)),QPoint(),QPoint(0,delta),Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier,Qt.ScrollPhase.NoScrollPhase,False)
        QApplication.sendEvent(w.view.viewport(),event);app.processEvents();after=w.view.mapToScene(position)
        assert (after-before).manhattanLength()*w.view.transform().m11()<2
