"""Missing computation pixels stay out of display, prompts and label output."""
import copy
from types import SimpleNamespace
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import Point,shape
from geoforma.raster import inspect_source,make_recipe,read_rgb
from geoforma.domain import new_project
from geoforma.storage import save_project
from geoforma.project_loading import prepare_project
from test_reference_missing_values import reference
from test_workbench import workbench


@pytest.mark.parametrize('crs',['EPSG:3857',None])
def test_computation_image_masks_tagged_pixels_in_display_and_model_input(tmp_path,crs):
    image,data=reference(tmp_path,crs=crs)
    image['model_recipe']=make_recipe(image,[1,1,1])
    assert image['model_recipe']['ranges'][0][0]>.1
    assert image['model_recipe']['validity_policy']['value']==-9999
    rgb,valid=read_rgb(image,[0,0,40,40])
    assert np.array_equal(valid,data!=-9999) and not rgb[~valid].any()
    reduced,small_valid=read_rgb(image,[0,0,40,40],max_size=20)
    assert not small_valid[7,14] and small_valid[7,12] and reduced[7,12,0]>140


def test_integer_tagged_nodata_is_read_without_nan_conversion_failure(tmp_path):
    path=tmp_path/'index.tif';data=np.full((10,10),42,dtype='int16');data[3,4]=-9999
    with rasterio.open(path,'w',driver='GTiff',width=10,height=10,count=1,dtype='int16',transform=from_origin(0,10,1,1)) as ds:
        ds.write(data,1);ds.update_tags(missing_value_encoding='-9999 stored as ordinary values; no TIFF NoData or mask')
    image=inspect_source(path);image['model_recipe']=make_recipe(image,[1,1,1])
    rgb,valid=read_rgb(image,[0,0,10,10]);assert not valid[3,4] and valid.sum()==99 and not rgb[3,4].any()


def test_unflagged_values_remain_valid_computation_data(tmp_path):
    image,_=reference(tmp_path,tag=False);image['model_recipe']=image['display_recipe']
    _,valid=read_rgb(image,[0,0,40,40]);assert valid.all()


def test_explicit_raster_mask_takes_precedence_over_conflicting_tag(tmp_path):
    image,_=reference(tmp_path)
    mask=np.full((40,40),255,dtype='uint8');mask[7,7]=0
    with rasterio.open(image['path'],'r+') as ds:ds.write_mask(mask)
    image=inspect_source(image['path']);image['model_recipe']=make_recipe(image,[1,1,1])
    _,valid=read_rgb(image,[0,0,40,40])
    assert valid[20,30] and not valid[7,7] and 'validity_policy' not in image['model_recipe']


def test_missing_pixel_prompt_reaches_sam_predictor():
    from geoforma.inference.engine import ModelEngine
    engine=ModelEngine();engine.prepare_backend=lambda *args:None
    valid=np.ones((10,10),bool);valid[3:6,4:7]=False
    engine.window_input=lambda *args:(np.zeros((10,10,3),np.uint8),valid)
    calls=[];engine.backend=SimpleNamespace(predict=lambda *args:(calls.append(args) or {'choices':[]}))
    task=SimpleNamespace(check=lambda:None,signals=SimpleNamespace(progress=SimpleNamespace(emit=lambda *args:None)))
    request={'window':[0,0,10,10],'points':[[4.5,3.5,1]],'box':None}
    engine.predict({}, {'checkpoint':'test'},request,task)
    assert len(calls)==1 and not calls[0][3][3,4]


def test_stale_recipe_cannot_reuse_previously_prepared_sam_features(tmp_path):
    from geoforma.inference.engine import ModelEngine
    image,_=reference(tmp_path);image['model_recipe']=copy.deepcopy(image['display_recipe'])
    engine=ModelEngine();calls=[];engine.prepare_model=lambda *args:calls.append(args)
    task=SimpleNamespace(check=lambda:None,signals=SimpleNamespace(progress=SimpleNamespace(emit=lambda *args:None)))
    with pytest.raises(ValueError,match='缺失值处理尚未更新'):engine.prepare_backend({},image,task)
    assert not calls


def test_sam_output_geometry_excludes_invalid_pixels():
    from geoforma.backend import SamBackend
    backend=SamBackend();backend.encode=lambda *args:True;backend.cache_key='key'
    backend.config={'device':'cpu','weights_sha256':'test','variant':'vit_b'}
    def predict(**kwargs):return np.ones((1,10,10),bool),np.array([.9]),np.zeros((1,256,256),np.float32)
    backend.predictor=SimpleNamespace(predict=predict)
    valid=np.ones((10,10),bool);valid[3:6,4:7]=False
    result=backend.predict({'width':10,'height':10},[0,0,10,10],np.zeros((10,10,3),np.uint8),valid,[[1.5,1.5,1]])
    polygon=shape(result['choices'][0]['geometry'])
    assert polygon.area==91 and not polygon.covers(Point(5,4)) and polygon.covers(Point(1,1))


def test_smoothing_cannot_expand_a_model_label_into_missing_pixels(tmp_path,monkeypatch):
    from shapely.geometry import box,mapping
    from geoforma import smoothing
    image,_=reference(tmp_path);image['model_recipe']=make_recipe(image,[1,1,1])
    original=box(20,5,38,35).difference(box(26,10,34,30))
    label={'id':'target','image_id':image['id'],'status':'confirmed','geometry':mapping(original)}
    monkeypatch.setattr(smoothing,'smooth_geometry',lambda *args:mapping(box(20,5,38,35)))
    result=smoothing.smooth_batch([label],1,image)[0]
    assert not shape(result['geometry']).covers(Point(30,20))


def test_manual_smoothing_handles_image_without_model_bands(tmp_path,monkeypatch):
    from shapely.geometry import box,mapping
    from geoforma import smoothing
    image,_=reference(tmp_path);image['model_recipe']=None;image['display_recipe']=None
    original=box(20,5,38,35).difference(box(26,10,34,30))
    label={'id':'target','image_id':image['id'],'status':'confirmed','geometry':mapping(original)}
    monkeypatch.setattr(smoothing,'smooth_geometry',lambda *args:mapping(box(20,5,38,35)))
    result=smoothing.smooth_batch([label],1,image)[0]
    assert not shape(result['geometry']).covers(Point(30,20))


@pytest.mark.parametrize('manual',[False,True])
def test_raster_export_preserves_manual_labels_on_missing_pixels(tmp_path,manual):
    from shapely.geometry import box,mapping
    from geoforma.exports import export_raster
    from test_spatial_storage import Task
    image,_=reference(tmp_path);image['model_recipe']=make_recipe(image,[1,1,1])
    label={'id':'target','image_id':image['id'],'status':'confirmed','class_id':1,'geometry':mapping(box(0,0,40,40))}
    if manual:label['editing_state']='manual'
    output=tmp_path/'labels.tif';export_raster(image,[label],output,Task())
    with rasterio.open(output) as ds:
        values=ds.read(1)
        assert ds.nodata==65535 and values[20,30]==(1 if manual else 65535) and values[20,20]==1


def test_manual_raster_export_needs_no_model_bands(tmp_path):
    from shapely.geometry import box,mapping
    from geoforma.exports import export_raster
    from test_spatial_storage import Task
    image,_=reference(tmp_path);image['model_recipe']=None;image['display_recipe']=None
    label={'id':'target','image_id':image['id'],'status':'confirmed','class_id':1,
           'editing_state':'manual','geometry':mapping(box(20,10,35,30))}
    output=tmp_path/'labels.tif';export_raster(image,[label],output,Task())
    with rasterio.open(output) as ds:assert ds.read(1)[20,30]==1


@pytest.mark.parametrize('native',[False,True])
def test_reshape_allows_manual_pixels_in_missing_area(tmp_path,native):
    from geoforma.reshape import reshape_raster
    from test_reshape import G,OUT
    image,_=reference(tmp_path)
    with rasterio.open(image['path'],'r+') as ds:
        data=ds.read(1);data[31,25]=-9999;ds.write(data,1)
        if native:ds.nodata=-9999
    image=inspect_source(image['path']);image['model_recipe']=make_recipe(image,[1,1,1])
    result=reshape_raster(image,G,OUT);geometry=shape(result['geometry'])
    assert geometry.covers(Point(25.5,31.5)) and geometry.covers(Point(23.5,31.5))


def test_old_project_invalidates_only_affected_model_cache(tmp_path):
    image,_=reference(tmp_path);image['model_recipe']=copy.deepcopy(image['display_recipe'])
    image.update(ready=True,prepared_full_signature='old',prepared_cache_revision='old')
    project=new_project();project['images']=[image];project['workspace']['image_id']=image['id']
    path=tmp_path/'work.geoforma.json';save_project(project,path)
    loaded=prepare_project(path,(100,100),read_frame=False)
    assert loaded.nodata_model_changed==(image['id'],) and loaded.nodata_migration_changed
    assert not loaded.image['ready'] and 'prepared_full_signature' not in loaded.image
    assert loaded.image['model_recipe']['ranges'][0][0]>.1
    assert loaded.image['model_recipe']['validity_policy']['value']==-9999
    assert image['ready'] and image['model_recipe']['ranges'][0][0]==-9999


def test_recovery_preserves_labels_and_invalidates_stale_model_draft(workbench,tmp_path):
    from shapely.geometry import box,mapping
    w,app,wait,errors=workbench
    image,_=reference(tmp_path);image['model_recipe']=copy.deepcopy(image['display_recipe'])
    image.update(ready=True,prepared_full_signature='old',prepared_cache_revision='old')
    project=new_project();project['images']=[image]
    project['labels']=[dict(id='saved',image_id=image['id'],status='confirmed',class_id=1,geometry=mapping(box(2,2,6,6)))]
    project['workspace'].update(image_id=image['id'],draft={'points':[[10,10,1]],'geometry':mapping(box(8,8,14,14))})
    path=tmp_path/'old.geoforma.json';save_project(project,path)
    assert w.open_project(path)
    assert len(w.project['labels'])==1 and w.project['labels'][0]['id']=='saved'
    assert w.draft['points']==[[10,10,1]] and w.draft['pending']
    assert not w.image['ready'] and w.dirty and not errors
