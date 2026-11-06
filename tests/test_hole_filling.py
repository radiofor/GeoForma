"""Hole editing and filling are optional, bounded, and undoable."""
import copy
from types import SimpleNamespace
import numpy as np
import pytest
from PySide6.QtTest import QTest
from shapely.geometry import Polygon,box,mapping,shape
from geoforma.hole_filling import fill_label_holes,fill_preview
from test_reshape import OUT,workbench,raster_image
from test_smoothing import settled
from test_smoothing_reshape_transition import delay_smoothing,wait_until


def test_geometry_fill_preserves_original_and_existing_blockers():
    source=mapping(box(0,0,10,10).difference(box(2,2,8,8)));before=copy.deepcopy(source)
    label={'id':'outer','geometry':source,'status':'confirmed','image_id':'image'}
    assert shape(fill_label_holes([label])[0]['geometry']).equals(box(0,0,10,10))
    blocker={'id':'inner','geometry':mapping(box(4,4,6,6)),'status':'confirmed','image_id':'image'}
    filled=shape(fill_label_holes([label,blocker])[0]['geometry'])
    assert filled.equals(box(0,0,10,10).difference(box(4,4,6,6))) and source==before
    simple={'id':'simple','geometry':mapping(box(0,0,1,1))};assert fill_label_holes([simple])[0] is simple


def test_preview_fills_internal_holes_without_changing_input():
    bitmap=np.zeros((10,10),np.uint8);bitmap[1:9,1:9]=255;bitmap[3:7,3:7]=0
    before=bitmap.copy();result=fill_preview(bitmap)
    assert result[3,3]==255 and result[4,4]==255 and result[0,0]==0 and np.array_equal(bitmap,before)


def test_preview_filling_keeps_four_connected_background_semantics():
    from PIL import Image,ImageDraw,ImageOps
    rng=np.random.default_rng(23)
    for _ in range(40):
        bitmap=(rng.random((16,16))>.55).astype('uint8')*255
        image=ImageOps.expand(Image.fromarray(bitmap),border=1,fill=0);ImageDraw.floodfill(image,(0,0),128)
        expected=(np.asarray(image)[1:-1,1:-1]!=128).astype('uint8')*255
        assert np.array_equal(fill_preview(bitmap),expected)


@pytest.mark.parametrize('prompt_box',[None,[0,0,10,10]])
def test_model_preview_fills_without_modifying_prediction(prompt_box):
    from geoforma.inference.engine import ModelEngine
    source=mapping(box(0,0,10,10).difference(box(2,2,8,8)))
    bitmap=np.ones((10,10),np.uint8)*255;bitmap[2:8,2:8]=0
    valid=np.ones((10,10),bool);valid[4:6,4:6]=False
    engine=ModelEngine();engine.prepare_backend=lambda *args:None
    engine.window_input=lambda *args:(None,valid)
    def predict(*args,on_mask=None,**kwargs):
        on_mask({'mask':bitmap,'window':[0,0,10,10]})
        return {'choices':[{'geometry':source,'pixels':64}]}
    engine.backend=SimpleNamespace(predict=predict,streaming_preview=True)
    previews=[];task=SimpleNamespace(check=lambda:None,signals=SimpleNamespace(progress=SimpleNamespace(emit=lambda *args:None),preview=SimpleNamespace(emit=previews.append)))
    request={'window':[0,0,10,10],'points':[[1,1,1]],'box':prompt_box,'fill_holes':True}
    result=engine.predict({}, {'checkpoint':'test'},request,task)
    assert previews[0]['mask'][3,3]==255 and previews[0]['mask'][4,4]==255
    assert shape(result['choices'][0]['geometry']).equals(shape(source))
    assert result['choices'][0]['pixels']==64 and len(shape(source).interiors)==1


def test_interactive_model_preview_fills_nodata_holes_only_in_display():
    from geoforma.inference.engine import ModelEngine
    bitmap=np.ones((10,10),np.uint8)*255;bitmap[2:8,2:8]=0;bitmap[0,0]=0
    valid=np.ones((10,10),bool);valid[4:6,4:6]=False
    engine=ModelEngine();engine.prepare_backend=lambda *args:None
    engine.window_input=lambda *args:(None,valid)
    engine.backend=SimpleNamespace(restore=lambda *args:True,predict=lambda *args,**kwargs:{'mask':bitmap,'window':[0,0,10,10]})
    task=SimpleNamespace(check=lambda:None)
    request={'window':[0,0,10,10],'points':[[1,1,1]],'fill_holes':True}
    preview=engine.preview({}, {'checkpoint':'test'},request,task)
    assert preview['mask'][3,3]==255 and preview['mask'][4,4]==255 and preview['mask'][0,0]==0
    assert bitmap[4,4]==0
    request['fill_holes']=False
    assert engine.preview({}, {'checkpoint':'test'},request,task)['mask'][4,4]==0


def test_auto_reshape_can_edit_a_hole_without_selecting_a_label(workbench):
    w,app,_=workbench;original=box(20,20,40,40).difference(box(25,25,35,35))
    w.fill_holes.setChecked(False);w.project['labels'][0]['geometry']=mapping(original);w.refresh_labels();settled(w,app)
    w.begin_reshape(auto=True)
    for x,y in [[27,33],[27,38],[33,38],[33,33]]:w.add_reshape_point(x,y)
    w.finish_reshape();wait_until(app,lambda:w.task is None)
    assert w.reshape_session is None and shape(w.project['labels'][0]['geometry']).area==282
    w.undo_context();assert shape(w.project['labels'][0]['geometry']).equals(original)


def test_hidden_hole_is_not_an_editable_boundary(workbench):
    w,app,_=workbench;original=box(20,20,40,40).difference(box(25,25,35,35))
    w.fill_holes.setChecked(True);w.project['labels'][0]['geometry']=mapping(original);w.refresh_labels();settled(w,app)
    w.begin_reshape(auto=True)
    for x,y in [[27,33],[27,38],[33,38],[33,33]]:w.add_reshape_point(x,y)
    w.finish_reshape();wait_until(app,lambda:w.task is None)
    assert w.reshape_session is not None and w.reshape_session.get('error')
    assert shape(w.project['labels'][0]['geometry']).equals(original)
    w.cancel_reshape();w.fill_holes.setChecked(False);settled(w,app)
    w.begin_reshape(auto=True)
    for x,y in [[27,33],[27,38],[33,38],[33,33]]:w.add_reshape_point(x,y)
    w.finish_reshape();wait_until(app,lambda:w.task is None)
    assert w.reshape_session is None and not shape(w.project['labels'][0]['geometry']).equals(original)


def test_crossing_outer_and_hidden_hole_preserves_unedited_inner_boundary():
    from geoforma.reshape import reshape_intent,reshape_patch
    original=box(20,20,40,40).difference(box(25,25,35,35))
    result=reshape_patch(reshape_intent(mapping(original),[[18,30],[42,30]],include_holes=False),{'width':100,'height':100})
    assert shape(result['geometry']).equals(original.intersection(box(20,30,40,40)))


@pytest.mark.parametrize('prompt_box',[None,[20,20,30,30]])
def test_model_point_or_box_prediction_save_and_reshape_preserves_hole(workbench,prompt_box):
    from geoforma.inference.engine import ModelEngine
    from geoforma.storage import save_project,load_project
    w,app,tmp=workbench;w.project['labels']=[];w.selected_id=None;w.selected_ids.clear()
    w.fill_holes.setChecked(True);w.smooth_enabled.setChecked(False)
    source=mapping(box(20,20,30,30).difference(box(24,24,26,26)))
    engine=ModelEngine();engine.prepare_backend=lambda *args:None
    engine.window_input=lambda *args:(None,np.ones((100,100),bool))
    engine.backend=SimpleNamespace(streaming_preview=False,predict=lambda *args:{'choices':[{'geometry':source,'pixels':96}],
        'window':[0,0,100,100],'key':'synthetic','cache_hit':False,'device':'cpu'})
    task=SimpleNamespace(check=lambda:None,signals=SimpleNamespace(progress=SimpleNamespace(emit=lambda *args:None)))
    points=[[22,22,1]] if prompt_box is None else []
    request={'window':[0,0,100,100],'points':points,'box':prompt_box,'fill_holes':True}
    result=engine.predict(w.image,{'checkpoint':''},request,task)
    w.draft={'points':points,'box':prompt_box,'pending':True};w.predicted(result);w.confirm()
    assert len(w.project['labels'])==1 and len(shape(w.project['labels'][0]['geometry']).interiors)==1
    settled(w,app)
    w.begin_reshape(auto=True)
    for x,y in OUT:w.add_reshape_point(x,y)
    w.finish_reshape();wait_until(app,lambda:w.task is None)
    raw=shape(w.project['labels'][0]['geometry'])
    assert raw.is_valid and len(raw.interiors)==1 and raw.bounds[3]>30
    for enabled in (False,True,False):
        w.fill_holes.setChecked(enabled);assert shape(w.project['labels'][0]['geometry']).equals(raw)
    w.capture_workspace();path=tmp/'prediction.gfm';save_project(w.project,path)
    assert shape(load_project(path)['labels'][0]['geometry']).equals(raw)


def test_option_persists_without_modifying_existing_labels(workbench):
    w,app,_=workbench;before=copy.deepcopy(w.project['labels'])
    assert w.fill_holes.isChecked()
    w.fill_holes.setChecked(False);w.capture_workspace()
    assert w.project['workspace']['fill_holes'] is False and w.project['labels']==before
    from geoforma.session_validation import validate_sessions
    validate_sessions(w.project)


def test_hole_option_survives_project_reopen(workbench):
    w,app,tmp=workbench;w.fill_holes.setChecked(False);w.capture_workspace()
    from geoforma.storage import save_project
    path=tmp/'holes.gfm';save_project(w.project,path)
    w.fill_holes.setChecked(True);assert w.open_project(path)
    assert not w.fill_holes.isChecked() and w.project['workspace']['fill_holes'] is False


def test_missing_hole_option_uses_new_default_when_reopened(workbench):
    w,app,tmp=workbench;w.capture_workspace();w.project['workspace'].pop('fill_holes',None)
    from geoforma.storage import save_project
    path=tmp/'missing-option.gfm';save_project(w.project,path)
    w.fill_holes.setChecked(False);assert w.open_project(path)
    assert w.fill_holes.isChecked()


def test_reshape_preserves_hole_with_fill_enabled_and_undo(workbench):
    w,app,_=workbench
    original=mapping(box(20,20,30,30).difference(box(24,24,26,26)))
    w.project['labels'][0]['geometry']=original;w.refresh_labels();w.fill_holes.setChecked(True)
    w.smooth_enabled.setChecked(False);settled(w,app);w.begin_reshape(auto=True)
    for x,y in OUT:w.add_reshape_point(x,y)
    w.finish_reshape();wait_until(app,lambda:w.task is None)
    result=w.project['labels'][0];assert result['status']=='confirmed' and len(shape(result['geometry']).interiors)==1
    assert shape(result['geometry']).area==120
    w.undo_context();assert shape(w.project['labels'][0]['geometry']).equals(shape(original))
    w.redo_context();assert len(shape(w.project['labels'][0]['geometry']).interiors)==1


def test_filled_reshape_keeps_previous_smoothed_outline_until_ready(workbench,monkeypatch):
    w,app,_=workbench;w.project['labels'][0]['geometry']=mapping(box(20,20,30,30).difference(box(24,24,26,26)))
    w.fill_holes.setChecked(True);w.smooth_enabled.setChecked(True);w.refresh_labels();settled(w,app)
    item=w.view.overlay_records['target'];previous=item.geometry_value;started,release=delay_smoothing(monkeypatch)
    try:
        w.begin_reshape(auto=True)
        for x,y in OUT:w.add_reshape_point(x,y)
        w.finish_reshape();wait_until(app,lambda:w.task is None);wait_until(app,started.is_set)
        assert len(shape(w.project['labels'][0]['geometry']).interiors)==1
        assert w.view.overlay_records['target'] is item and item.geometry_value is previous
    finally:
        release.set();settled(w,app)
    assert not shape(item.geometry_value).interiors
