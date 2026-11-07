"""Reference reads never create a disk cache or modify source files."""
from pathlib import Path
import hashlib
import numpy as np
import rasterio
from rasterio.transform import from_origin
from geoforma.raster import inspect_source
from geoforma.reference_images import display_descriptor,read_display,reference_recipe


def test_reference_recipe_and_reprojection_are_read_only(tmp_path):
    def make(path,width,pixel):
        with rasterio.open(path,'w',driver='GTiff',width=width,height=width,count=1,
                           dtype='float32',nodata=-9999,crs='EPSG:3857',
                           transform=from_origin(0,32,pixel,pixel)) as ds:
            ds.write(np.arange(width*width,dtype='float32').reshape(width,width),1)
        return inspect_source(path)
    base=make(tmp_path/'main.tif',32,1)
    reference=make(tmp_path/'reference.tif',64,.5)
    before={p.relative_to(tmp_path):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in tmp_path.rglob('*') if p.is_file()}
    reference['display_recipe']=reference_recipe(reference)
    rgb,valid=read_display(display_descriptor(base,reference),[0,0,32,32],max_size=16)
    assert rgb.shape==(16,16,3) and valid.any()
    after={p.relative_to(tmp_path):hashlib.sha256(p.read_bytes()).hexdigest()
           for p in tmp_path.rglob('*') if p.is_file()}
    assert after==before
