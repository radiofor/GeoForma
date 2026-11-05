"""Hole editing and filling are optional, bounded, and undoable."""
import copy
from types import SimpleNamespace
import numpy as np
from PySide6.QtTest import QTest
from shapely.geometry import Polygon,box,mapping,shape
from geoforma.hole_filling import fill_holes,fill_prediction,fill_preview
from test_reshape import OUT,workbench,raster_image
from test_smoothing import settled
from test_smoothing_reshape_transition import delay_smoothing,wait_until


def test_geometry_fill_preserves_original_and_existing_blockers():
    source=mapping(box(0,0,10,10).difference(box(2,2,8,8)));before=copy.deepcopy(source)
    assert shape(fill_holes(source)).equals(box(0,0,10,10))
    filled=shape(fill_holes(source,[mapping(box(4,4,6,6))]))
    assert filled.equals(box(0,0,10,10).difference(box(4,4,6,6))) and source==before
    simple=mapping(box(0,0,1,1));assert fill_holes(simple) is simple


def test_prediction_and_preview_do_not_fill_invalid_pixels():
    source=mapping(box(0,0,10,10).difference(box(2,2,8,8)))
    valid=np.ones((10,10),bool);valid[4:6,4:6]=False
    expected=box(0,0,10,10).difference(box(4,4,6,6))
    assert shape(fill_prediction(source,valid,[0,0,10,10])).equals(expected)
    bitmap=np.zeros((10,10),np.uint8);bitmap[1:9,1:9]=255;bitmap[3:7,3:7]=0
    before=bitmap.copy();result=fill_preview(bitmap,valid)
    assert result[3,3]==255 and result[4,4]==0 and result[0,0]==0 and np.array_equal(bitmap,before)


def test_preview_filling_keeps_four_connected_background_semantics():
    from PIL import Image,ImageDraw,ImageOps
    rng=np.random.default_rng(23)
    for _ in range(40):
        bitmap=(rng.random((16,16))>.55).astype('uint8')*255
        image=ImageOps.expand(Image.fromarray(bitmap),border=1,fill=0);ImageDraw.floodfill(image,(0,0),128)
        expected=(np.asarray(image)[1:-1,1:-1]!=128).astype('uint8')*255
        assert np.array_equal(fill_preview(bitmap),expected)


def test_model_preview_and_final_result_use_same_fill_setting():
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
    request={'window':[0,0,10,10],'points':[],'fill_holes':True}
    result=engine.predict({}, {'checkpoint':'test'},request,task)
    assert previews[0]['mask'][3,3]==255 and previews[0]['mask'][4,4]==0
    assert shape(result['choices'][0]['geometry']).equals(box(0,0,10,10).difference(box(4,4,6,6)))
    assert result['choices'][0]['pixels']==96 and len(shape(source).interiors)==1


def test_auto_reshape_can_edit_a_hole_without_selecting_a_label(workbench):
    w,app,_=workbench;original=box(20,20,40,40).difference(box(25,25,35,35))
    w.project['labels'][0]['geometry']=mapping(original);w.refresh_labels()
    w.begin_reshape(auto=True)
    for x,y in [[27,33],[27,38],[33,38],[33,33]]:w.add_reshape_point(x,y)
    w.finish_reshape();wait_until(app,lambda:w.task is None)
    assert w.reshape_session is None and shape(w.project['labels'][0]['geometry']).area==282
    w.undo_context();assert shape(w.project['labels'][0]['geometry']).equals(original)


def test_option_persists_without_modifying_existing_labels(workbench):
    w,app,_=workbench;before=copy.deepcopy(w.project['labels'])
    assert not w.fill_holes.isChecked()
    w.fill_holes.setChecked(True);w.capture_workspace()
    assert w.project['workspace']['fill_holes'] is True and w.project['labels']==before
    from geoforma.session_validation import validate_sessions
    validate_sessions(w.project)


def test_hole_option_survives_project_reopen(workbench):
    w,app,tmp=workbench;w.fill_holes.setChecked(True);w.capture_workspace()
    from geoforma.storage import save_project
    path=tmp/'holes.gfm';save_project(w.project,path)
    w.fill_holes.setChecked(False);assert w.open_project(path)
    assert w.fill_holes.isChecked() and w.project['workspace']['fill_holes'] is True


def test_fill_after_reshape_is_undoable_and_keeps_saved_status(workbench):
    w,app,_=workbench
    original=mapping(box(20,20,30,30).difference(box(24,24,26,26)))
    w.project['labels'][0]['geometry']=original;w.refresh_labels();w.fill_holes.setChecked(True)
    w.smooth_enabled.setChecked(False);w.begin_reshape(auto=True)
    for x,y in OUT:w.add_reshape_point(x,y)
    w.finish_reshape();wait_until(app,lambda:w.task is None)
    result=w.project['labels'][0];assert result['status']=='confirmed' and len(shape(result['geometry']).interiors)==0
    assert shape(result['geometry']).area==124
    w.undo_context();assert shape(w.project['labels'][0]['geometry']).equals(shape(original))
    w.redo_context();assert len(shape(w.project['labels'][0]['geometry']).interiors)==0


def test_filled_reshape_keeps_previous_smoothed_outline_until_ready(workbench,monkeypatch):
    w,app,_=workbench;w.project['labels'][0]['geometry']=mapping(box(20,20,30,30).difference(box(24,24,26,26)))
    w.fill_holes.setChecked(True);w.smooth_enabled.setChecked(True);w.refresh_labels();settled(w,app)
    item=w.view.overlay_records['target'];previous=item.geometry_value;started,release=delay_smoothing(monkeypatch)
    try:
        w.begin_reshape(auto=True)
        for x,y in OUT:w.add_reshape_point(x,y)
        w.finish_reshape();wait_until(app,lambda:w.task is None);wait_until(app,started.is_set)
        assert not shape(w.project['labels'][0]['geometry']).interiors
        assert w.view.overlay_records['target'] is item and item.geometry_value is previous
    finally:
        release.set();settled(w,app)
    assert not shape(item.geometry_value).interiors
