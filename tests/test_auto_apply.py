import os,copy,time,threading
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import numpy as np
from types import SimpleNamespace
from PySide6.QtWidgets import QApplication
from shapely.geometry import box,mapping
from geoforma.window import MainWindow
from geoforma.services import ModelEngine

def wait(app,condition,seconds=4):
    deadline=time.monotonic()+seconds
    while not condition() and time.monotonic()<deadline:app.processEvents();time.sleep(.005)
    assert condition()

def window():
    app=QApplication.instance() or QApplication([]);w=MainWindow(auto_prepare=False);w.autosave=lambda:None
    w.image={'id':'test','width':1000,'height':1000,'ready':True,'model_recipe':None,'display_recipe':None}
    return w,app

def prediction(request):
    return {'choices':[{'geometry':mapping(box(100,100,200+len(request['points']),200)),'score':.9,'edge':False}],
            'window':request['window'],'key':'test','cache_hit':True,'device':'cpu'}

def test_auto_apply_coalesces_clicks_and_undo_and_box_without_saving():
    w,app=window();calls=[];w.service.predict=lambda image,config,request,task:(calls.append(copy.deepcopy(request)) or prediction(request))
    w.auto_apply.setChecked(True);w.add_point(120,120,1);w.add_point(150,150,0)
    assert not w.apply_button.isEnabled()
    wait(app,lambda:len(calls)==1 and w.task is None)
    assert len(calls[0]['points'])==2 and not w.draft['pending'] and not w.project['labels']
    w.undo_prompt();wait(app,lambda:len(calls)==2 and w.task is None);assert len(calls[-1]['points'])==1
    w.add_box([100,100,200,200]);wait(app,lambda:len(calls)==3 and w.task is None);assert calls[-1]['box']==[100,100,200,200]
    w.auto_apply.setChecked(False);w.add_point(160,160,1)
    assert w.apply_button.isEnabled()
    for _ in range(40):app.processEvents();time.sleep(.005)
    assert len(calls)==3 and w.draft['pending'];w.dirty=False;w.close();app.processEvents()

def test_more_clicks_during_prediction_replace_stale_result():
    w,app=window();calls=[];started=threading.Event();release=threading.Event()
    def predict(image,config,request,task):
        calls.append(copy.deepcopy(request))
        if len(calls)==1:started.set();release.wait(3)
        return prediction(request)
    w.service.predict=predict;w.auto_apply.setChecked(True);w.add_point(120,120,1)
    wait(app,started.is_set);w.add_point(130,130,1);w.add_point(140,140,0);release.set()
    wait(app,lambda:len(calls)==2 and w.task is None and not w.draft['pending'])
    assert len(calls[-1]['points'])==3 and not w.project['labels'];w.dirty=False;w.close();app.processEvents()

def test_automatic_candidate_can_receive_points_without_saving_early():
    w,app=window();candidate={'id':'candidate','image_id':'test','status':'candidate','class_id':None,'geometry':mapping(box(100,100,250,250)),'window':[-128,-128,1024,1024]}
    w.project['labels']=[candidate];before=copy.deepcopy(candidate);w.select_items('labels',['candidate'])
    calls=[];w.service.predict=lambda image,config,request,task:(calls.append(copy.deepcopy(request)) or prediction(request))
    w.edit_selected(locate=False)
    w.auto_apply.setChecked(True);w.add_point(120,120,1);w.add_point(230,230,0)
    wait(app,lambda:len(calls)==1 and w.task is None and not w.draft.get('pending'))
    assert calls[0]['points']==[[120,120,1],[230,230,0]] and calls[0]['seed']==candidate['geometry']
    assert tuple(calls[0]['window'])==(-128,-128,1024,1024) and not calls[0].get('full_image')
    assert w.draft['base_id']=='candidate' and w.project['labels']==[before]
    w.dirty=False;w.close();app.processEvents()

def test_removed_guided_generation_has_no_execution_side_effects():
    import pytest
    engine=ModelEngine()
    with pytest.raises(ValueError,match='已移除'):
        engine.guided_automatic({}, {}, [], 8, 'detail', {}, None)
