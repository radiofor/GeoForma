import copy,time
from pathlib import Path
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from PySide6.QtTest import QTest
from geoforma.reference_images import matching_references,reference_recipe,display_descriptor,read_display
from geoforma.raster import inspect_source,make_recipe
from geoforma.model_requests import model_image
from geoforma.storage import save_project,load_project
from test_workbench import workbench


def raster(path,value=0.2,width=60,transform=None,crs='EPSG:3857'):
    path.parent.mkdir(parents=True,exist_ok=True)
    with rasterio.open(path,'w',driver='GTiff',width=width,height=width,count=1,dtype='float32',crs=crs,transform=transform or from_origin(0,120,2,2),nodata=-9999) as ds:
        data=np.full((width,width),value,dtype='float32');data[0,0]=-9999;ds.write(data,1)
    image=inspect_source(path);image['model_recipe']=make_recipe(image,[1,1,1]);image['display_recipe']=reference_recipe(image);image['ready']=True
    return image


def test_match_and_reproject_to_calculation_grid_without_model_changes(tmp_path):
    base=raster(tmp_path/'rgb'/'tile.tif')
    ref=raster(tmp_path/'ndwi'/'tile.tif',width=120,transform=from_origin(0,120,1,1));ref['group']='NDWI'
    before=copy.deepcopy(base);project={'references':[ref]}
    assert matching_references(project,base)==[ref]
    assert not matching_references(project,dict(base,path='other.tif'))
    descriptor=display_descriptor(base,ref);rgb,valid=read_display(descriptor,[0,0,60,60],max_size=40)
    assert rgb.shape==(40,40,3) and valid.shape==(40,40) and valid.any()
    assert base==before and model_image(base)==model_image(before) and '_reference' not in model_image(descriptor)


@pytest.mark.parametrize('window,size',[([0,0,0,20],None),([0,0,20,20],0),([0,0,20,20],float('nan')),([0,0,10000,10000],None)])
def test_reference_and_main_display_share_allocation_limits(tmp_path,window,size):
    image=raster(tmp_path/'source.tif');reference=dict(image,group='NDWI')
    for descriptor in (image,display_descriptor(image,reference)):
        with pytest.raises(ValueError):read_display(descriptor,window,max_size=size)


def test_reference_stretch_keeps_narrow_index_range_and_reads_each_band_once(tmp_path,monkeypatch):
    image=raster(tmp_path/'ndwi.tif');real_open=rasterio.open;reads=[]
    class Reader:
        def __enter__(self):self.source=real_open(image['path']);return self
        def __exit__(self,*args):self.source.close()
        def __getattr__(self,name):return getattr(self.source,name)
        def read(self,band,**kwargs):reads.append(band);return self.source.read(band,**kwargs)
    monkeypatch.setattr(rasterio,'open',lambda *args,**kwargs:Reader())
    recipe=reference_recipe(image)
    assert reads==[1] and recipe['bands']==[1,1,1]
    assert recipe['ranges'][0]==recipe['ranges'][1]==recipe['ranges'][2]
    assert 0<recipe['ranges'][0][1]-recipe['ranges'][0][0]<.00001


def test_multiple_types_switch_only_basemap_and_restore_partial_matches(workbench,tmp_path):
    w,app,wait,errors=workbench
    base=raster(tmp_path/'rgb'/'tile.tif');other=raster(tmp_path/'rgb'/'other.tif')
    ndwi=raster(tmp_path/'NDWI'/'tile.tif',0.4);ndvi=raster(tmp_path/'NDVI'/'tile.tif',0.7)
    w.project['images']=[base,other];w.refresh_images();w.images.setCurrentRow(0)
    reports=[];w.show_import_report=lambda *args:reports.append(args)
    w.import_reference_paths([ndwi['path']],'NDWI');wait()
    w.import_reference_paths([ndvi['path']],'NDVI');wait()
    assert len(w.project['references'])==2 and w.reference_switches.isVisible()
    assert w.main_image_button.isVisible() and w.main_image_button.text()=='主影像'
    assert [w.reference_switches.layout().itemAt(i).widget().text() for i in range(2)]==['NDWI','NDVI']
    from shapely.geometry import box,mapping
    w.project['labels']=[dict(id='label',image_id=base['id'],annotation_mode='individual',status='confirmed',class_id=1,geometry=mapping(box(10,10,20,20)))]
    w.draft={'points':[[15,15,1]],'box':[10,10,30,30]};w.refresh_labels()
    item=w.view.overlay_records['label'];point=w.view.point_records[0];bounds=w.view.box_item
    navigation=w.view.capture_navigation();before=copy.deepcopy(model_image(base))
    # This fixture suppresses scheduled raster requests; use the real display path here.
    from geoforma.controllers.display import DisplayWorkflow
    w.request_render=lambda overview=False:DisplayWorkflow.request_render(w,overview)
    for ref in [w.project['references'][0],w.project['references'][1],None,w.project['references'][0]]:
        w.switch_reference(ref)
        deadline=time.monotonic()+4
        while w.reference_transition_pending or w.render_task:
            app.processEvents();QTest.qWait(2);assert time.monotonic()<deadline
        QTest.qWait(160);app.processEvents()
        assert w.view.overlay_records['label'] is item and w.view.point_records[0] is point and w.view.box_item is bounds
        assert item.zValue()>w.view.base_item.zValue() and point.zValue()>item.zValue()
        assert w.view.capture_navigation()==navigation and model_image(base)==before
    w.capture_workspace();save_project(w.project,w.project_path);loaded=load_project(w.project_path)
    assert len(loaded['references'])==2
    w.images.setCurrentRow(1);QTest.qWait(180);app.processEvents()
    assert not w.reference_switches.isVisible() and w.main_image_button.isVisible() and w.display_reference is None
    QTest.qWait(20);app.processEvents();w.images.setCurrentRow(0)
    assert w.reference_switches.isVisible() and w.display_reference is None
    assert not reports and not errors


def test_same_group_new_file_replaces_match_and_failed_file_does_not_remove_existing(workbench,tmp_path):
    w,app,wait,errors=workbench;reference=raster(tmp_path/'ndwi'/'tile.tif')
    base=raster(tmp_path/'rgb'/'tile.tif');w.project['images']=[base];w.refresh_images();w.images.setCurrentRow(0)
    reports=[];w.show_import_report=lambda *args:reports.append(args)
    w.import_reference_paths([reference['path']],'NDWI');wait()
    w.import_reference_paths([reference['path'],str(tmp_path/'absent'/'tile.tif')],'NDWI');wait()
    assert len(w.project['references'])==1 and len(reports)==1 and not errors


def test_reference_extent_is_clipped_and_uncovered_area_is_transparent(tmp_path):
    base=raster(tmp_path/'base'/'tile.tif')
    wide=raster(tmp_path/'wide'/'tile.tif',width=120,transform=from_origin(-60,180,2,2))
    wide['group']='wide'
    rgb,valid=read_display(display_descriptor(base,wide),[0,0,60,60],max_size=60)
    assert rgb.shape==(60,60,3) and valid.all()
    small=raster(tmp_path/'small'/'tile.tif',width=30);small['group']='small'
    rgb,valid=read_display(display_descriptor(base,small),[0,0,60,60],max_size=60)
    assert valid[2:28,2:28].all() and not valid[:,31:].any() and not valid[31:,:].any()


def test_different_crs_is_reprojected_to_the_main_extent(tmp_path):
    from rasterio.warp import transform_bounds
    from rasterio.transform import from_bounds
    base=raster(tmp_path/'base'/'tile.tif')
    bounds=transform_bounds('EPSG:3857','EPSG:4326',0,0,120,120)
    ref=raster(tmp_path/'ref'/'tile.tif',width=80,crs='EPSG:4326',transform=from_bounds(*bounds,80,80));ref['group']='NDWI'
    rgb,valid=read_display(display_descriptor(base,ref),[0,0,60,60],max_size=60)
    assert rgb.shape==(60,60,3) and valid[2:-2,2:-2].all()
