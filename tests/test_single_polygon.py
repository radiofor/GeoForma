import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import copy,time,threading
from types import SimpleNamespace
import numpy as np
import pytest
from shapely.geometry import box, mapping, shape, MultiPolygon
from geoforma.single_polygon import select_polygon,single_mask
from geoforma.backend import SamBackend,mask_geometry
from PySide6.QtWidgets import QApplication
from geoforma.window import MainWindow


def test_positive_points_take_priority_over_area_and_holes_survive():
    small=box(1,1,5,5).difference(box(2,2,3,3));large=box(10,10,30,30)
    geometry=mapping(MultiPolygon([small,large]))
    selected=shape(select_polygon(geometry,[[1.5,1.5,1],[20,20,0]]))
    assert selected.equals(small) and len(selected.interiors)==1
    assert shape(select_polygon(geometry)).equals(large)
    assert shape(select_polygon(geometry,[[1.5,1.5,1],[20,20,1],[21,21,1]])).equals(large)


def test_mask_four_connectivity_offset_and_no_smoothing():
    mask=np.zeros((10,10),bool);mask[1:4,1:4]=True;mask[2,2]=False;mask[7:9,7:9]=True
    selected=single_mask(mask,[100,200,10,10],[[107.5,207.5,1]])
    assert selected.sum()==4 and shape(mask_geometry(selected,[100,200,10,10],{'width':1000,'height':1000})).bounds==(107,207,109,209)
    diagonal=np.eye(2,dtype=bool)
    assert single_mask(diagonal,[0,0,2,2],[]).sum()==1
    assert not single_mask(np.zeros((2,2),bool),[0,0,2,2],[]).any()


@pytest.mark.parametrize('preview',[False,True])
def test_native_prediction_and_fast_feedback_apply_same_policy(preview):
    mask=np.zeros((10,10),bool);mask[1:5,1:5]=True;mask[7:9,7:9]=True
    backend=SamBackend();backend.encode=lambda *a:True;backend.cache_key='test'
    backend.config={'device':'cpu','weights_sha256':'test','variant':'vit_b'}
    backend.predictor=SimpleNamespace(predict=lambda **kw:(mask[None],np.array([.9]),np.zeros((1,256,256),np.float32)))
    feedback=[]
    result=backend.predict({'width':10,'height':10},[0,0,10,10],np.zeros((10,10,3),np.uint8),np.ones((10,10),bool),[[7.5,7.5,1]],preview=preview,on_mask=feedback.append,single_polygon=True)
    bitmap=result['mask'] if preview else feedback[0]['mask']
    assert bitmap[200,200]>0 and bitmap[60,60]==0
    if not preview:assert result['choices'][0]['geometry']['type']=='Polygon' and result['choices'][0]['pixels']==4


@pytest.fixture
def workbench():
    app=QApplication.instance() or QApplication([]);w=MainWindow(auto_prepare=False);w.autosave=lambda:None
    w.auto_apply.setChecked(False);w.image={'id':'image','width':1000,'height':1000,'ready':True,'model_recipe':None,'display_recipe':None}
    yield w,app
    w.image=None;w.dirty=False;w.close();app.processEvents()


def test_option_request_pending_and_mode_visibility(workbench):
    w,app=workbench;assert w.single_polygon.isChecked() and w.smooth_enabled.isChecked();w.single_polygon.setChecked(False)
    w.add_point(100,100,1);calls=[]
    w.service.predict=lambda image,config,request,task:(calls.append(copy.deepcopy(request)) or dict(choices=[dict(geometry=mapping(box(90,90,110,110)))],window=request['window'],key='test',cache_hit=True,device='cpu'))
    w.run=lambda title,work,done,**kw:done(work(None))
    w.predict();assert not w.draft['pending']
    w.single_polygon.setChecked(True);assert w.draft['pending'] and not w.confirm_button.isEnabled()
    w.predict();assert calls[-1]['single_polygon']
    w.capture_workspace();assert w.project['workspace']['single_polygon']
    w.clear_draft();assert not w.single_polygon.isHidden() and w.mode_index==0
    assert not w.single_polygon.isHidden() and w.single_polygon.isChecked()


def test_save_after_overlap_clip_is_polygon_and_preserves_other_labels(workbench):
    w,app=workbench;category=w.classes.currentData()
    blocker=dict(id='blocker',image_id='image',class_id=category,status='confirmed',annotation_mode='individual',geometry=mapping(box(4,0,6,10)))
    w.project['labels']=[copy.deepcopy(blocker)];w.single_polygon.setChecked(True)
    w.draft={'geometry':mapping(box(0,0,10,10)),'points':[[8,5,1]],'pending':False}
    w.confirm()
    saved=next(l for l in w.project['labels'] if l['id']!='blocker')
    assert saved['geometry']['type']=='Polygon' and shape(saved['geometry']).equals(box(6,0,10,10))
    assert w.project['labels'][0]==blocker and saved['model']['single_polygon']
    w.undo_label();assert w.project['labels']==[blocker]
    w.redo_label();assert len(w.project['labels'])==2


@pytest.mark.parametrize('enabled',[False,True])
@pytest.mark.parametrize('same_class',[False,True])
def test_overlap_component_policy_follows_checkbox(workbench,enabled,same_class):
    from geoforma.label_conflicts import assert_no_overlaps
    w,app=workbench;category=w.classes.currentData()
    blocker=dict(id='blocker',image_id='image',class_id=category if same_class else 99,status='confirmed',annotation_mode='individual',geometry=mapping(box(2,0,4,10)))
    w.project['labels']=[copy.deepcopy(blocker)];w.single_polygon.setChecked(enabled)
    w.draft={'geometry':mapping(box(0,0,10,10)),'points':[[1,5,1]],'pending':False};w.confirm()
    assert w.project['labels'][0]==blocker
    saved=w.project['labels'][1]
    expected=box(4,0,10,10) if enabled else MultiPolygon([box(0,0,2,10),box(4,0,10,10)])
    from shapely.ops import unary_union
    assert unary_union([shape(l['geometry']) for l in w.project['labels'][1:]]).equals(expected)
    assert len(w.project['labels'])==(2 if enabled else 3)
    assert all(l['geometry']['type']=='Polygon' for l in w.project['labels']);assert_no_overlaps(w.project['labels'])
    assert saved['model']['overlap_resolution']['saved_area']==(60 if enabled else 80)
    assert saved['model']['overlap_resolution']['component_policy']==('largest_area' if enabled else 'keep_all')
    w.undo_label();assert w.project['labels']==[blocker]
    w.redo_label();assert unary_union([shape(l['geometry']) for l in w.project['labels'][1:]]).equals(expected)


def test_fully_covered_label_retains_draft_and_history(workbench,monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    w,app=workbench;messages=[]
    monkeypatch.setattr(QMessageBox,'information',lambda *args:messages.append(args[2]))
    blocker=dict(id='blocker',image_id='image',class_id=w.classes.currentData(),status='confirmed',annotation_mode='individual',geometry=mapping(box(0,0,10,10)))
    w.project['labels']=[copy.deepcopy(blocker)];w.draft={'geometry':mapping(box(1,1,5,5)),'pending':False}
    draft=copy.deepcopy(w.draft);w.confirm()
    assert w.project['labels']==[blocker] and w.draft==draft and not w.label_undo and len(messages)==1


def test_unchecked_saves_independent_polygons(workbench):
    w,app=workbench;w.single_polygon.setChecked(False);geometry=mapping(MultiPolygon([box(1,1,3,3),box(5,5,9,9)]))
    w.draft={'geometry':geometry,'pending':False};w.confirm()
    assert len(w.project['labels'])==2 and w.labels_table.rowCount()==2
    assert all(l['geometry']['type']=='Polygon' for l in w.project['labels'])


def test_edited_label_follows_current_single_polygon_setting(workbench):
    w,app=workbench;w.single_polygon.setChecked(True)
    category=w.classes.currentData()
    blocker=dict(id='blocker',image_id='image',class_id=category,status='confirmed',annotation_mode='individual',geometry=mapping(box(2,0,4,10)))
    target=dict(id='target',image_id='image',class_id=category,status='confirmed',annotation_mode='individual',geometry=mapping(box(0,0,10,10)))
    w.project['labels']=[copy.deepcopy(blocker),target]
    w.draft={'base_id':'target','geometry':target['geometry'],'pending':False};w.confirm()
    saved=next(l for l in w.project['labels'] if l['id']=='target')
    assert w.project['labels'][0]==blocker
    assert saved['geometry']['type']=='Polygon' and shape(saved['geometry']).area==60
    assert saved['model']['overlap_resolution']['component_policy']=='largest_area'


def test_option_survives_project_reopen_and_defaults_off_for_legacy(workbench,tmp_path):
    from geoforma.storage import save_project
    w,app=workbench;w.image=None;w.single_polygon.setChecked(True)
    w.project_path=tmp_path/'single.gfm';w.save()
    w.single_polygon.blockSignals(True);w.single_polygon.setChecked(False);w.single_polygon.blockSignals(False)
    w.open_project(w.project_path);assert w.single_polygon.isChecked()
    w.single_polygon.setChecked(False);w.smooth_enabled.setChecked(False);w.save()
    w.open_project(w.project_path);assert not w.single_polygon.isChecked() and not w.smooth_enabled.isChecked()
    w.project['workspace'].pop('single_polygon',None);save_project(w.project,w.project_path)
    w.open_project(w.project_path);assert not w.single_polygon.isChecked()
    w.new();assert w.single_polygon.isChecked() and w.smooth_enabled.isChecked()
    assert w.smooth_enabled.isChecked()


def test_non_streaming_backend_needs_no_new_argument():
    from geoforma.inference.engine import ModelEngine
    engine=ModelEngine();engine.prepare_backend=lambda *a:None
    engine.window_input=lambda *a:(None,np.ones((1024,1024),bool))
    geometry=mapping(MultiPolygon([box(0,0,10,10),box(20,20,22,22)]))
    # Backends without streaming preview use positional arguments only.
    engine.backend=SimpleNamespace(predict=lambda *args:{'choices':[{'geometry':geometry,'pixels':104}]})
    task=SimpleNamespace(signals=SimpleNamespace(progress=SimpleNamespace(emit=lambda *a:None)),check=lambda:None)
    result=engine.predict({}, {'checkpoint':'test'}, {'window':[0,0,1024,1024],'points':[[21,21,1]],'single_polygon':True},task)
    assert result['choices'][0]['geometry']['type']=='Polygon' and result['choices'][0]['pixels']==4


@pytest.mark.parametrize('preview',[False,True])
def test_single_preview_stays_connected_after_downsampling_a_thin_bridge(preview):
    mask=np.zeros((1024,1024),bool)
    mask[384:640,128:384]=True;mask[384:640,640:896]=True;mask[511,384:640]=True
    assert shape(mask_geometry(mask,[0,0,1024,1024],{'width':1024,'height':1024})).geom_type=='Polygon'
    backend=SamBackend();backend.encode=lambda *args:True;backend.cache_key='test'
    backend.config={'device':'cpu','weights_sha256':'test','variant':'vit_b'}
    backend.predictor=SimpleNamespace(predict=lambda **kwargs:(mask[None],np.array([.9]),np.zeros((1,256,256),np.float32)))
    feedback=[];points=[[200.5,450.5,1],[700.5,450.5,1],[300.5,700.5,0],[800.5,700.5,0]]
    result=backend.predict({'width':1024,'height':1024},[0,0,1024,1024],np.zeros((1024,1024,3),np.uint8),
                           np.ones_like(mask),points,preview=preview,on_mask=feedback.append,single_polygon=True)
    bitmap=result['mask'] if preview else feedback[0]['mask']
    assert shape(mask_geometry(bitmap>0,[0,0,256,256],{'width':256,'height':256})).geom_type=='Polygon'
    if not preview:
        assert result['choices'][0]['geometry']['type']=='Polygon'
        assert shape(result['choices'][0]['geometry']).equals(shape(mask_geometry(mask,[0,0,1024,1024],{'width':1024,'height':1024})))


def test_ui_prediction_boundary_rejects_multipart_when_single_is_checked(workbench):
    w,app=workbench;w.single_polygon.setChecked(True)
    w.draft={'points':[[15,15,1],[16,16,1],[45,45,1],[60,60,0]],'pending':True}
    geometry=mapping(MultiPolygon([box(10,10,20,20),box(40,40,50,50)]))
    result=dict(choices=[dict(geometry=geometry,pixels=200,score=.9)],window=[0,0,1024,1024],key='test',cache_hit=True,device='cpu')
    w.predicted(result)
    assert w.draft['geometry']['type']=='Polygon' and shape(w.draft['geometry']).equals(box(10,10,20,20))
    assert result['choices'][0]['geometry']['type']=='MultiPolygon'


def settle_until(app,condition):
    deadline=time.monotonic()+5
    while not condition():
        app.processEvents();time.sleep(.003);assert time.monotonic()<deadline


@pytest.mark.parametrize('automatic',[False,True])
def test_multiple_positive_negative_points_keep_one_displayed_and_saved_region(workbench,automatic):
    w,app=workbench;w.auto_apply.setChecked(automatic);w.single_polygon.setChecked(True)
    calls=[];geometry=mapping(MultiPolygon([box(100,100,200,200),box(300,100,400,200)]))
    def predict(image,config,request,task):
        calls.append(copy.deepcopy(request))
        return dict(choices=[dict(geometry=geometry,score=.9,pixels=20000)],window=request['window'],key='test',cache_hit=True,device='cpu')
    w.service.predict=predict
    for point in ([120,120,1],[150,150,1],[330,130,1],[650,650,0],[350,150,0]):w.add_point(*point)
    if not automatic:w.predict()
    settle_until(app,lambda:bool(calls) and w.task is None and not w.draft.get('pending'))
    assert w.single_polygon.isChecked() and calls[-1]['single_polygon'] and len(calls[-1]['points'])==5
    assert w.draft['geometry']['type']=='Polygon' and w.view.overlay_records['__draft'].geometry_value['type']=='Polygon'
    assert shape(w.draft['geometry']).equals(box(100,100,200,200))
    w.confirm();assert w.project['labels'][0]['geometry']['type']=='Polygon' and w.project['labels'][0]['model']['single_polygon']


def test_more_points_during_auto_prediction_cannot_restore_multipart_result(workbench):
    w,app=workbench;w.auto_apply.setChecked(True);w.single_polygon.setChecked(True)
    started=threading.Event();release=threading.Event();calls=[]
    geometry=mapping(MultiPolygon([box(100,100,200,200),box(300,100,400,200)]))
    def predict(image,config,request,task):
        calls.append(copy.deepcopy(request))
        if len(calls)==1:started.set();assert release.wait(5)
        return dict(choices=[dict(geometry=geometry,score=.9)],window=request['window'],key='test',cache_hit=True,device='cpu')
    w.service.predict=predict;w.add_point(120,120,1)
    try:
        settle_until(app,started.is_set)
        for point in ([150,150,1],[330,130,1],[650,650,0],[350,150,0]):w.add_point(*point)
    finally:release.set()
    settle_until(app,lambda:len(calls)==2 and w.task is None and not w.draft.get('pending'))
    assert all(request['single_polygon'] for request in calls) and len(calls[-1]['points'])==5
    assert w.draft['geometry']['type']=='Polygon' and w.view.overlay_records['__draft'].geometry_value['type']=='Polygon'


def test_streaming_preview_boundary_scales_points_before_single_filter(workbench):
    w,app=workbench;w.single_polygon.setChecked(True)
    bitmap=np.zeros((64,128),np.uint8);bitmap[8:24,8:24]=255;bitmap[40:56,96:112]=255
    window=[100,200,2048,1024];w.draft={'points':[[1700,900,1],[1750,950,1],[1800,920,1],[300,400,0]],'pending':True}
    seen=[];release=threading.Event();w.view.show_preview=lambda mask,*args:seen.append(mask)
    def work(task):
        task.signals.preview.emit(dict(mask=bitmap,window=window));assert release.wait(5)
    try:
        w.run('逐个分割',work,lambda result:None,kind='interactive')
        settle_until(app,lambda:bool(seen))
        visible=shape(mask_geometry(seen[0]>0,[0,0,128,64],{'width':128,'height':64}))
        assert visible.geom_type=='Polygon' and visible.bounds==(96,40,112,56)
    finally:release.set()
    settle_until(app,lambda:w.task is None)
