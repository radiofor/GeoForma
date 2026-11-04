import copy
from pathlib import Path
import numpy as np
import pytest
import rasterio
from rasterio.transform import Affine
from rasterio.features import rasterize
from shapely.geometry import box,mapping,shape
from osgeo import ogr
from geoforma.domain import new_project,prompt_window,tiles
from geoforma.raster import inspect_source,make_recipe,read_rgb
from geoforma.storage import save_project,load_project
from geoforma.exports import export_raster,export_vector


class Quiet:
    def emit(self,*args):pass
class Task:
    class signals:progress=Quiet()
    def check(self):pass


@pytest.fixture
def source(tmp_path):
    path=tmp_path/'source.tif';transform=Affine(7,1,500000,2,-7,3200000)
    pixels=np.full((3,67,91),90,np.uint16);pixels[:,:3,:]=0
    with rasterio.open(path,'w',driver='GTiff',width=91,height=67,count=3,dtype='uint16',crs='EPSG:32645',transform=transform,nodata=0) as ds:ds.write(pixels)
    image=inspect_source(path);image['model_recipe']=make_recipe(image,[1,2,3]);image['display_recipe']=copy.deepcopy(image['model_recipe']);return image


def test_native_grid_and_vector_roundtrip(source,tmp_path):
    labels=[{'id':'a','image_id':source['id'],'geometry':mapping(box(10,10,17,16)),'class_id':1,'status':'confirmed'},
            {'id':'b','image_id':source['id'],'geometry':mapping(box(14,14,20,20)),'class_id':2,'status':'confirmed'}]
    from geoforma.label_conflicts import resolve
    labels[1]['geometry']=resolve(labels[1],labels)['geometry']
    expected=rasterize([(v['geometry'],v['class_id']) for v in labels],out_shape=(67,91),dtype='uint16');expected[:3]=65535
    tif=tmp_path/'labels.tif';export_raster(source,labels,tif,Task())
    with rasterio.open(tif) as ds:
        assert np.array_equal(ds.read(1),expected)
        assert ds.read(1)[14,14]==1 and ds.read(1)[18,18]==2
        assert ds.transform==Affine(*source['transform']);assert ds.nodata==65535;assert ds.crs.to_epsg()==32645
    gpkg=tmp_path/'labels.gpkg';export_vector(source,labels,gpkg,'',Task())
    from shapely.affinity import affine_transform
    inverse=~Affine(*source['transform']);a,b,c,d,e,f=list(inverse)[:6]
    ds=ogr.Open(str(gpkg));layer=ds.GetLayer(0)
    for feature,label in zip(layer,labels):
        import json
        geom=shape(json.loads(feature.GetGeometryRef().ExportToJson()));pixels=affine_transform(geom,[a,b,d,e,c,f]);assert pixels.hausdorff_distance(shape(label['geometry']))<1e-7
    ds=None


def test_boundless_nodata_and_display_independence(source):
    rgb,valid=read_rgb(source,(-10,-8,40,40));assert rgb.shape==(40,40,3);assert not valid[:11].any();assert not valid[:,:10].any();assert valid[20,20]
    old=copy.deepcopy(source['model_recipe']);source['display_recipe']['bands']=[3,2,1];assert source['model_recipe']==old


def test_window_prompt_coverage_and_scale():
    w=prompt_window([[767.5,767.5,1]]);assert w==(-128,-128,1024,1024)
    enlarged=prompt_window([[767.5,767.5,1],[2200,800,1]],current=w);assert enlarged[2]>1024
    assert all(enlarged[0]<=x<enlarged[0]+enlarged[2] and enlarged[1]<=y<enlarged[1]+enlarged[3] for x,y,_ in [[767.5,767.5,1],[2200,800,1]])
    assert len(list(tiles((0,0,1958,1957),1958,1957)))==9


def test_project_roundtrip_does_not_create_backup(source,tmp_path):
    project=new_project();project['images']=[source];project['labels']=[{'id':'saved','image_id':source['id'],'status':'confirmed','class_id':1,'geometry':mapping(box(10,10,20,20))}]
    path=tmp_path/'project.gfm';save_project(project,path);loaded=load_project(path);assert loaded['images'][0]['path']==source['path'];assert loaded['labels'][0]['id']=='saved'
    project['name']='changed';save_project(project,path)
    assert load_project(path)['name']=='changed' and not Path(str(path)+'.bak').exists()


def test_cancel_keeps_existing_export(source,tmp_path):
    from geoforma.tasks import Cancelled
    class Cancel(Task):
        def check(self):raise Cancelled()
    path=tmp_path/'existing.tif';path.write_bytes(b'original')
    with pytest.raises(Cancelled):export_raster(source,[],path,Cancel())
    assert path.read_bytes()==b'original';assert not path.with_name('existing.partial.tif').exists()


def test_export_cannot_overwrite_source(source):
    before=Path(source['path']).read_bytes()
    with pytest.raises(ValueError,match='覆盖'):export_raster(source,[],source['path'],Task())
    assert Path(source['path']).read_bytes()==before
