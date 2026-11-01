import os,copy
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from types import SimpleNamespace
import numpy as np
import pytest
from shapely.geometry import box,mapping,shape
from PySide6.QtWidgets import QApplication
from geoforma.window import MainWindow
from geoforma.backend import SamBackend
from geoforma.prompt_bounds import contains_point,clip_geometry,bounded_mask


@pytest.fixture
def workbench():
    app=QApplication.instance() or QApplication([]);w=MainWindow(auto_prepare=False);w.autosave=lambda:None
    w.auto_apply.setChecked(False);w.image={'id':'image','width':1000,'height':1000,'ready':True,'model_recipe':None,'display_recipe':None}
    yield w,app
    w.image=None;w.dirty=False;w.close();app.processEvents()


def test_outside_points_are_rejected_without_history_or_inference(workbench):
    w,app=workbench;w.add_box([100,100,200,200]);w.add_point(150,150,1)
    before=copy.deepcopy(w.draft);undo=copy.deepcopy(w.prompt_undo);revision=w.prompt_revision
    for x,y in [(99,150),(201,150),(150,99),(150,201)]:
        for label in [0,1]:w.add_point(x,y,label)
    assert w.draft==before and w.prompt_undo==undo and w.prompt_revision==revision
    assert not w.auto_apply_timer.isActive()
    assert contains_point(w.draft['box'],100,200)


def test_new_box_replaces_old_box_filters_points_and_undo_restores(workbench):
    w,app=workbench;w.add_point(110,110,1);w.add_point(190,190,0);w.add_box([100,100,200,200])
    w.draft['window']=[-128,-128,1024,1024];old=copy.deepcopy(w.draft)
    w.add_box([180,180,300,300])
    assert w.draft['box']==[180,180,300,300] and w.draft['points']==[[190,190,0]] and w.draft['window'] is None
    assert not contains_point(w.draft['box'],110,110)
    w.undo_prompt();assert w.draft['box']==old['box'] and w.draft['points']==old['points'] and w.draft['window']==old['window']
    w.redo_prompt();assert w.draft['box']==[180,180,300,300] and w.draft['points']==[[190,190,0]]
    calls=[]
    w.service.predict=lambda image,config,request,task:(calls.append(request) or dict(choices=[],window=request['window'],key='test',cache_hit=True,device='cpu'))
    w.run=lambda title,work,done,**kw:done(work(None))
    w.predict();assert calls[-1]['box']==[180,180,300,300] and calls[-1]['points']==[[190,190,0]]
    w.clear_box();w.add_point(110,110,1);assert len(w.draft['points'])==2


def test_pending_draft_and_saved_label_stay_inside_fractional_box(workbench):
    w,app=workbench;w.draft={'geometry':mapping(box(0,0,100,100)),'pending':False}
    bounds=[10.25,20.75,80.5,90.5];w.add_box(bounds)
    assert shape(w.draft['geometry']).equals(box(*bounds)) and w.draft['pending']
    # Save-time defense also handles an older or external result outside the box.
    w.draft['geometry']=mapping(box(0,0,100,100));w.draft['pending']=False;w.confirm()
    saved=w.project['labels'][0];assert shape(saved['geometry']).equals(box(*bounds))
    w.undo_label();assert not w.project['labels'];w.redo_label();assert shape(w.project['labels'][0]['geometry']).equals(box(*bounds))


@pytest.mark.parametrize('preview',[False,True])
def test_native_mask_and_exact_geometry_are_box_bounded(preview):
    backend=SamBackend();backend.encode=lambda *a:True;backend.cache_key='test'
    backend.config={'device':'cpu','weights_sha256':'test','variant':'vit_b'};calls=[]
    def predict(**kwargs):
        calls.append(kwargs);return np.ones((1,10,10),bool),np.array([.9]),np.zeros((1,256,256),np.float32)
    backend.predictor=SimpleNamespace(predict=predict);feedback=[];bounds=[102.25,203.75,106.5,208.5]
    result=backend.predict({'width':1000,'height':1000},[100,200,10,10],np.zeros((10,10,3),np.uint8),np.ones((10,10),bool),[[104,205,1],[101,201,0]],box=bounds,preview=preview,on_mask=feedback.append)
    assert calls[0]['point_labels'].tolist()==[1]
    bitmap=result['mask'] if preview else feedback[0]['mask']
    assert not bitmap[:50].any() and not bitmap[:,:50].any() and bitmap[150,100]>0
    if preview:assert result['box']==bounds
    else:assert shape(result['choices'][0]['geometry']).equals(box(*bounds)) and feedback[0]['box']==bounds


def test_legacy_backend_results_are_clipped_without_new_protocol_arguments():
    from geoforma.services import ModelEngine
    engine=ModelEngine();engine.prepare_backend=lambda *args:None;engine.window_input=lambda *args:(None,np.ones((1024,1024),bool));calls=[]
    def predict(*args):
        calls.append(args);return {'choices':[{'geometry':mapping(box(0,0,30,30))}]}
    engine.backend=SimpleNamespace(predict=predict)
    task=SimpleNamespace(signals=SimpleNamespace(progress=SimpleNamespace(emit=lambda *args:None)),check=lambda:None)
    result=engine.predict({}, {'checkpoint':'test'},{'window':[0,0,1024,1024],'box':[10,10,20,20],'points':[[15,15,1],[25,25,0]]},task)
    assert calls[0][4]==[[15,15,1]] and shape(result['choices'][0]['geometry']).equals(box(10,10,20,20))


def test_preview_renderer_clips_low_resolution_feedback_to_exact_box(workbench):
    w,app=workbench;w.view.show_preview(np.ones((256,256),np.uint8),[0,0,1024,1024],[10.25,20.75,80.5,90.5])
    item=w.view.preview_item;assert item.mapRectToScene(item.clip_rect).getRect()==(10.25,20.75,70.25,69.75)
    w.view.show_preview(np.ones((256,256),np.uint8),[0,0,1024,1024]);assert w.view.preview_item is item and item.clip_rect is None


def test_box_clipping_preserves_holes_and_no_box_changes_nothing():
    geometry=mapping(box(0,0,10,10).difference(box(4,4,6,6)))
    assert clip_geometry(geometry,None) is geometry
    clipped=shape(clip_geometry(geometry,[2,2,8,8]));assert len(clipped.interiors)==1 and clipped.area==32
    assert clip_geometry(geometry,[20,20,30,30]) is None
    mask=np.ones((3,3),bool);assert bounded_mask(mask,[10,20,3,3],None) is mask
