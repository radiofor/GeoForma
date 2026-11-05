"""Avoid duplicate raster work while preserving pixels and source checks."""
import copy
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from geoforma.raster import inspect_source, read_rgb, validate_source
from geoforma.reference_images import display_descriptor, read_display


@pytest.fixture
def image(tmp_path):
    path=tmp_path/'image.tif'
    with rasterio.open(path,'w',driver='GTiff',width=8,height=8,count=1,dtype='uint8',transform=from_origin(0,8,1,1)) as source:
        source.write(np.arange(64,dtype='uint8').reshape(8,8),1)
    image=inspect_source(path)
    image['model_recipe']={'bands':[1,1,1],'ranges':[[0,64],[0,64],[0,32]]}
    image['display_recipe']=copy.deepcopy(image['model_recipe'])
    return image


def test_source_validation_opens_once_and_checks_grid_and_fingerprint(image,monkeypatch):
    real_open=rasterio.open;calls=[]
    def counted(*args,**kwargs):
        calls.append(args[0]);return real_open(*args,**kwargs)
    monkeypatch.setattr(rasterio,'open',counted)
    missing,stamp=validate_source(image)
    assert missing is None and stamp==image['fingerprint'] and len(calls)==1
    changed=dict(image,width=9)
    with pytest.raises(ValueError,match='网格已改变'):validate_source(changed)
    with real_open(image['path'],'r+') as source:source.write(np.full((8,8),7,dtype='uint8'),1)
    assert validate_source(image)[1]!=image['fingerprint']


def test_main_reuses_stretch_only_for_matching_band_and_range(image,monkeypatch):
    original=np.subtract;calls=[]
    def counted(*args,**kwargs):
        calls.append(True);return original(*args,**kwargs)
    monkeypatch.setattr(np,'subtract',counted)
    rgb,valid=read_rgb(image,[0,0,8,8])
    assert len(calls)==2 and valid.all()
    assert np.array_equal(rgb[:,:,0],rgb[:,:,1])
    assert rgb[2,0].tolist()==[63,63,127]


@pytest.mark.parametrize('reference',[False,True])
def test_all_valid_integer_raster_skips_mask_reads(image,monkeypatch,reference):
    original=rasterio.open;calls=[]
    class Source:
        def __init__(self,source):self.source=source
        def __enter__(self):return self
        def __exit__(self,*args):self.source.close()
        def __getattr__(self,name):return getattr(self.source,name)
        def read_masks(self,*args,**kwargs):calls.append('band');return self.source.read_masks(*args,**kwargs)
        def dataset_mask(self,*args,**kwargs):calls.append('dataset');return self.source.dataset_mask(*args,**kwargs)
    monkeypatch.setattr(rasterio,'open',lambda *args,**kwargs:Source(original(*args,**kwargs)))
    rgb,valid=(read_display(display_descriptor(image,dict(image,group='reference')),[0,0,8,8]) if reference else read_rgb(image,[0,0,8,8]))
    assert not calls and valid.all() and rgb[2,0].tolist()==[63,63,127]


def test_reference_reuses_matching_stretch_and_keeps_distinct_ranges(image,monkeypatch):
    original=np.clip;calls=[]
    def counted(*args,**kwargs):
        calls.append(True);return original(*args,**kwargs)
    monkeypatch.setattr(np,'clip',counted)
    rgb,valid=read_display(display_descriptor(image,dict(image,group='reference')),[0,0,8,8])
    assert len(calls)==2 and valid.all()
    assert np.array_equal(rgb[:,:,0],rgb[:,:,1])
    assert rgb[2,0].tolist()==[63,63,127]


def test_aligned_reference_avoids_warp_and_preserves_pixels_and_mask(tmp_path,monkeypatch):
    import geoforma.reference_images as reference_module
    path=tmp_path/'aligned.tif';values=np.arange(64,dtype='uint8').reshape(8,8)
    with rasterio.open(path,'w',driver='GTiff',width=8,height=8,count=1,dtype='uint8',crs='EPSG:3857',transform=from_origin(0,8,1,1)) as source:
        source.write(values,1);mask=np.full((8,8),255,dtype='uint8');mask[3,4]=0;source.write_mask(mask)
    image=inspect_source(path);image['display_recipe']={'bands':[1,1,1],'ranges':[[0,64]]*3}
    expected=read_rgb(image,[0,0,8,8],image['display_recipe'],8)
    monkeypatch.setattr(reference_module,'WarpedVRT',lambda *args,**kwargs:pytest.fail('aligned source should not be reprojected'))
    actual=read_display(display_descriptor(image,dict(image,group='reference')),[0,0,8,8],max_size=8)
    assert np.array_equal(actual[0],expected[0]) and np.array_equal(actual[1],expected[1])


def test_reference_with_different_grid_still_uses_warp(tmp_path,monkeypatch):
    import geoforma.reference_images as reference_module
    path=tmp_path/'shifted.tif'
    with rasterio.open(path,'w',driver='GTiff',width=8,height=8,count=1,dtype='uint8',crs='EPSG:3857',transform=from_origin(1,8,1,1)) as source:
        source.write(np.ones((8,8),dtype='uint8'),1)
    reference=inspect_source(path);reference['display_recipe']={'bands':[1,1,1],'ranges':[[0,2]]*3};reference['group']='reference'
    image=dict(reference,transform=list(from_origin(0,8,1,1))[:6]);called=[];original=reference_module.WarpedVRT
    def warp(*args,**kwargs):called.append(True);return original(*args,**kwargs)
    monkeypatch.setattr(reference_module,'WarpedVRT',warp)
    read_display(display_descriptor(image,reference),[0,0,8,8],max_size=8)
    assert called==[True]


@pytest.mark.parametrize('size',[4,8,16])
def test_aligned_reference_matches_warped_pixels_with_explicit_mask(tmp_path,size):
    from rasterio.vrt import WarpedVRT
    from rasterio.enums import Resampling
    from rasterio.windows import Window
    path=tmp_path/'masked.tif';values=np.arange(64,dtype='uint8').reshape(8,8)
    with rasterio.open(path,'w',driver='GTiff',width=8,height=8,count=1,dtype='uint8',crs='EPSG:3857',transform=from_origin(0,8,1,1)) as source:
        source.write(values,1);mask=np.full((8,8),255,dtype='uint8');mask[2:5,3:6]=0;source.write_mask(mask)
    image=inspect_source(path);image['display_recipe']={'bands':[1,1,1],'ranges':[[0,64]]*3}
    actual=read_display(display_descriptor(image,dict(image,group='reference')),[0,0,8,8],max_size=size)
    result_size=min(size,8)
    with rasterio.open(path) as source, WarpedVRT(source,crs='EPSG:3857',transform=source.transform,width=8,height=8,resampling=Resampling.bilinear,add_alpha=True) as vrt:
        array=vrt.read(1,window=Window(0,0,8,8),out_shape=(result_size,result_size),masked=True,resampling=Resampling.bilinear)
        vals=array.astype('float32').filled(float('nan'))
        valid=(~np.ma.getmaskarray(array)&np.isfinite(vals)) & (vrt.read(vrt.count,window=Window(0,0,8,8),out_shape=(result_size,result_size),resampling=Resampling.nearest)>0)
        channel=np.nan_to_num(np.clip(vals*255/64,0,255)).astype('uint8')
    assert np.array_equal(actual[1],valid) and np.array_equal(actual[0][:,:,0],channel)


def test_raster_export_reuses_open_vrt_and_protects_its_current_sources(image,tmp_path,monkeypatch):
    from rasterio.shutil import copy as raster_copy
    from shapely.geometry import box,mapping
    from geoforma.exports import export_raster
    vrt=tmp_path/'source.vrt';raster_copy(image['path'],vrt,driver='VRT')
    source=inspect_source(vrt);source['assigned_crs']='EPSG:3857'
    source['model_recipe']=image['model_recipe']
    # The source protection must inspect the current VRT, even if its saved list is stale.
    source['source_paths']=[str(vrt)]
    label={'id':'label','image_id':source['id'],'status':'confirmed','class_id':1,'geometry':mapping(box(1,1,3,3))}
    task=SimpleNamespace(check=lambda:None,signals=SimpleNamespace(progress=SimpleNamespace(emit=lambda *args:None)))
    real_open=rasterio.open;opened=[]
    def counted(path,*args,**kwargs):
        opened.append(Path(path).resolve());return real_open(path,*args,**kwargs)
    monkeypatch.setattr(rasterio,'open',counted)
    output=tmp_path/'labels.tif';export_raster(source,[label],output,task)
    assert opened.count(vrt.resolve())==1
    with real_open(output) as result:assert result.read(1)[1,1]==1
    with pytest.raises(ValueError,match='不能覆盖源影像'):
        export_raster(source,[label],image['path'],task)
