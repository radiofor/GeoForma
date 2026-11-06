"""Manual reshapes must not resurrect image no-data blocks as holes."""
import copy
import json
import time

import numpy as np
import pytest
import rasterio
from osgeo import ogr
from rasterio.transform import Affine
from shapely.affinity import affine_transform
from shapely.geometry import Point,box,mapping,shape

from test_reshape import workbench
from test_smoothing import settled
from test_spatial_storage import Task


@pytest.fixture
def raster_image(tmp_path):
    from geoforma.raster import inspect_source,make_recipe
    path=tmp_path/'synthetic.tif'
    pixels=np.full((3,100,100),100,np.uint8)
    pixels[:,20:31,35:41]=0
    with rasterio.open(path,'w',driver='GTiff',width=100,height=100,count=3,dtype='uint8',
                       crs='EPSG:3857',transform=Affine(2,.3,100,.2,-2,200),nodata=0) as ds:
        ds.write(pixels)
    image=inspect_source(path);image['ready']=True
    image['model_recipe']=make_recipe(image,[1,2,3]);image['display_recipe']=copy.deepcopy(image['model_recipe'])
    return image


def test_cut_and_redraw_nodata_hole_stays_filled_in_display_save_and_export(workbench):
    from geoforma.storage import save_project,load_project
    from geoforma.smoothing import smooth_batch
    from geoforma.exports import export_vector

    w,app,tmp=workbench;w.single_polygon.setChecked(False);w.smooth_enabled.setChecked(True)
    hole=box(35,20,41,31);point=Point(38.5,25.5)
    w.project['labels'][0]['geometry']=mapping(box(10,10,50,50).difference(hole));w.refresh_labels();settled(w,app)
    def reshape(stroke,alternate=False):
        w.begin_reshape(auto=True)
        for x,y in stroke:w.add_reshape_point(x,y)
        if alternate:w.reshape_alternate()
        w.finish_reshape();deadline=time.monotonic()+8
        while w.task and time.monotonic()<deadline:app.processEvents();time.sleep(.002)
        assert w.task is None and w.reshape_session is None
        settled(w,app)
    reshape([[30,5],[30,55]],True)
    reshape([[29,12],[45,12],[45,48],[29,48]])
    assert len(w.project['labels'])==1
    raw=shape(w.project['labels'][0]['geometry']);assert raw.covers(point)
    displayed=shape(w.view.overlay_records['target'].geometry_value)
    assert displayed.covers(point), '平滑显示重新挖掉手动覆盖的无数据区域'
    w.capture_workspace();path=tmp/'project.gfm';save_project(w.project,path)
    stored=json.loads(path.read_text(encoding='utf-8'))['labels'][0]
    assert shape(stored['geometry']).covers(point)
    assert shape(load_project(path)['labels'][0]['geometry']).covers(point)
    assert w.open_project(path)
    settled(w,app)
    smooth_shape=shape(w.view.overlay_records['target'].geometry_value)
    assert smooth_shape.covers(point) and not smooth_shape.equals(raw)
    w.smooth_enabled.setChecked(False);app.processEvents()
    assert shape(w.view.overlay_records['target'].geometry_value).equals(raw)
    w.smooth_enabled.setChecked(True);settled(w,app)
    assert shape(w.view.overlay_records['target'].geometry_value).covers(point)
    labels=smooth_batch(w.current_labels(),w.smooth_value.value(),w.image)
    target=tmp/'labels.gpkg';export_vector(w.image,labels,target,'',Task(),w.project['classes'])
    dataset=ogr.Open(str(target));feature=dataset.GetLayer(0).GetNextFeature()
    world=shape(json.loads(feature.GetGeometryRef().ExportToJson()))
    a,b,c,d,e,f=(~Affine(*w.image['transform']))[:6]
    assert affine_transform(world,[a,b,d,e,c,f]).covers(point)
