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


def test_reference_reuses_matching_stretch_and_keeps_distinct_ranges(image,monkeypatch):
    original=np.clip;calls=[]
    def counted(*args,**kwargs):
        calls.append(True);return original(*args,**kwargs)
    monkeypatch.setattr(np,'clip',counted)
    rgb,valid=read_display(display_descriptor(image,dict(image,group='reference')),[0,0,8,8])
    assert len(calls)==2 and valid.all()
    assert np.array_equal(rgb[:,:,0],rgb[:,:,1])
    assert rgb[2,0].tolist()==[63,63,127]


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
