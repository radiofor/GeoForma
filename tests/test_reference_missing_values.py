"""Explicitly declared reference missing values remain separate from real indices."""
import copy
import hashlib
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from geoforma.raster import inspect_source
from geoforma.reference_images import display_descriptor,read_display,reference_recipe


def reference(tmp_path,*,crs='EPSG:3857',tag=True,all_missing=False):
    path=tmp_path/'index.tif';data=np.full((40,40),.8,dtype='float32');data[:,:20]=.2
    data[10:30,26:34]=-9999
    if all_missing:data[:]=-9999
    with rasterio.open(path,'w',driver='GTiff',width=40,height=40,count=1,dtype='float32',
                       transform=from_origin(0,40,1,1),crs=crs) as ds:
        ds.write(data,1)
        if tag:ds.update_tags(missing_value_encoding='-9999 stored as ordinary values; no TIFF NoData or mask')
    image=inspect_source(path)
    # A previously saved project can retain a range polluted by the missing value.
    image['display_recipe']={'bands':[1,1,1],'ranges':[[-9999,.8]]*3,'format':'RGB uint8','nodata_fill':0}
    image['group']='NDWI'
    return image,data


@pytest.mark.parametrize('crs',['EPSG:3857',None])
def test_missing_pixels_are_masked_and_saved_bad_stretch_is_recomputed(tmp_path,crs):
    ref,data=reference(tmp_path,crs=crs);before=copy.deepcopy(ref)
    raw_hash=hashlib.sha256((tmp_path/'index.tif').read_bytes()).hexdigest()
    fresh=reference_recipe(ref)
    assert fresh['ranges'][0][0]>.1 and fresh['ranges'][0][1]<.9
    rgb,valid=read_display(display_descriptor(ref,ref),[0,0,40,40])
    assert np.array_equal(valid,data!=-9999)
    assert rgb[20,25,0]>240 and rgb[20,19,0]<15
    assert ref==before and hashlib.sha256((tmp_path/'index.tif').read_bytes()).hexdigest()==raw_hash


def test_downsampling_does_not_blend_missing_values_into_valid_neighbors(tmp_path):
    ref,_=reference(tmp_path)
    rgb,valid=read_display(display_descriptor(ref,ref),[0,0,40,40],max_size=20)
    assert not valid[7,14] and valid[7,12]
    assert rgb[7,12,0]>240


def test_unmarked_negative_values_are_not_guessed_to_be_nodata(tmp_path):
    ref,_=reference(tmp_path,tag=False)
    _,valid=read_display(display_descriptor(ref,ref),[0,0,40,40])
    assert valid.all()


@pytest.mark.parametrize('crs',['EPSG:3857',None])
def test_explicit_raster_mask_is_kept_when_tag_contradicts_it(tmp_path,crs):
    ref,_=reference(tmp_path,crs=crs)
    mask=np.full((40,40),255,dtype='uint8');mask[7,7]=0
    with rasterio.open(ref['path'],'r+') as ds:ds.write_mask(mask)
    _,valid=read_display(display_descriptor(ref,ref),[0,0,40,40])
    assert valid[20,30] and not valid[7,7]


def test_entirely_missing_tagged_reference_can_still_be_displayed(tmp_path):
    ref,_=reference(tmp_path,all_missing=True)
    recipe=reference_recipe(ref)
    assert recipe['ranges']==[[0.,1.]]*3
    _,valid=read_display(display_descriptor(ref,ref),[0,0,40,40])
    assert not valid.any()
