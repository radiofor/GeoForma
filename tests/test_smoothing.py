"""Actual geometry, reversible display, storage, mode isolation and export checks."""
import copy,json,time
import numpy as np
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from shapely.geometry import box,mapping,shape,Polygon,MultiPolygon
from geoforma.smoothing import smooth_geometry,smooth_batch,settings
from geoforma.storage import save_project,load_project,project_snapshot
from test_workbench import workbench,fake_image
from test_reshape import raster_image


def label(identifier,geometry,mode='individual'):
    return dict(id=identifier,image_id='one',class_id=1,status='confirmed',annotation_mode=mode,geometry=mapping(geometry))


@pytest.fixture
def smooth_workbench(workbench):
    w,app,wait,errors=workbench;w.smooth_enabled.setChecked(False);im=fake_image('one');im['ready']=True
    w.project['images']=[im];w.refresh_images();w.images.setCurrentRow(0)
    w.project['labels']=[label('a',box(20,20,80,80)),label('b',box(80,20,140,80))]
    w.refresh_labels();wait()
    yield w,app,wait,errors
    w.smoother.stop();w.smoother.pool.waitForDone(5000)
    for _ in range(3):app.processEvents()


def settled(w,app):
    deadline=time.monotonic()+10
    while w.smoother.timer.isActive() or w.smoother.task:
        app.processEvents();QTest.qWait(2)
        assert time.monotonic()<deadline
    for _ in range(3):app.processEvents()


def test_smoothing_reduces_steps_and_bounds_displacement():
    g=Polygon([(0,0),(20,0),*[(20-y//2,y) for y in range(1,20)],(0,20),(0,0)])
    result=shape(smooth_geometry(mapping(g),1.))
    assert result.is_valid and not result.equals(g) and result.length<g.length
    assert result.hausdorff_distance(g)<1.1


def test_small_parts_holes_box_and_nonoverlap_survive():
    source=MultiPolygon([box(0,0,20,20).difference(box(5,5,8,8)),box(30,30,31,31)])
    g=shape(smooth_geometry(mapping(source),5))
    assert g.geom_type=='MultiPolygon' and len(g.geoms)==2
    assert sum(len(p.interiors) for p in g.geoms)==1 and min(p.area for p in g.geoms)>.49
    records=[dict(label('a',box(0,0,20,20)),box=[0,0,20,20]),label('b',box(20,0,40,20))]
    result=smooth_batch(records,2,{'width':40,'height':40})
    assert shape(result[0]['geometry']).difference(box(0,0,20,20)).area==0
    assert shape(result[0]['geometry']).intersection(shape(result[1]['geometry'])).area==0


def test_manual_reshape_is_not_clipped_to_its_old_prompt_box(monkeypatch):
    from geoforma import smoothing
    original=box(5,5,15,15);record=dict(label('manual',original),box=[5,5,10,10],editing_state='manual')
    monkeypatch.setattr(smoothing,'_smooth_shape',lambda geometry,*args:geometry)
    result=smooth_batch([record],1,{'width':20,'height':20})
    assert shape(result[0]['geometry']).equals(original)


def test_checkbox_updates_all_items_in_place_and_off_restores_exact_sources(smooth_workbench):
    w,app,wait,errors=smooth_workbench;original=copy.deepcopy(w.project['labels'])
    items={key:value for key,value in w.view.overlay_records.items()}
    w.smooth_enabled.setChecked(True);settled(w,app)
    assert set(w.view.overlay_records)==set(items)
    for source in original:
        item=w.view.overlay_records[source['id']]
        assert item is items[source['id']] and not shape(item.geometry_value).equals(shape(source['geometry']))
    w.smooth_enabled.setChecked(False);app.processEvents()
    assert w.project['labels']==original
    for source in original:assert w.view.overlay_records[source['id']].geometry_value is w.project['labels'][int(source['id']=='b')]['geometry']
    assert not errors


def test_rapid_value_changes_publish_only_latest_and_modes_stay_independent(smooth_workbench):
    w,app,wait,errors=smooth_workbench
    w.smooth_enabled.setChecked(True);w.smooth_value.setValue(2);w.smooth_value.setValue(3);settled(w,app)
    actual=w.view.overlay_records['a'].geometry_value
    expected=smooth_batch(w.project['labels'],3,w.image)[0]['geometry']
    assert shape(actual).equals_exact(shape(expected),1e-9)
    w.refresh_labels();w.update_controls();settled(w,app)
    assert w.smooth_enabled.isChecked() and w.smooth_value.value()==3
    assert not errors


def test_fractional_project_smoothing_is_rejected(smooth_workbench,tmp_path):
    w,app,wait,errors=smooth_workbench;project=copy.deepcopy(w.project)
    project['smoothing']['individual']['value']=.5
    path=tmp_path/'invalid.gfm';path.write_text(json.dumps(project),encoding='utf-8')
    with pytest.raises(ValueError,match='整数像素'):load_project(path)


def test_project_file_materializes_checkbox_state_and_preserves_sources(smooth_workbench,tmp_path):
    w,app,wait,errors=smooth_workbench;raw=copy.deepcopy(w.project['labels'])
    w.project['labels'].append(label('other',box(160,20,220,80)))
    w.smooth_enabled.setChecked(True);settled(w,app)
    snapshot=project_snapshot(w.project);path=tmp_path/'smooth.gfm';save_project(snapshot,path)
    data=json.loads(path.read_text(encoding='utf-8'))
    assert not shape(data['labels'][0]['geometry']).equals(shape(raw[0]['geometry']))
    assert shape(data['labels'][0]['source_geometry']).equals(shape(raw[0]['geometry']))
    assert not shape(data['labels'][2]['geometry']).equals(box(160,20,220,80))
    assert shape(data['labels'][2]['source_geometry']).equals(box(160,20,220,80))
    restored=load_project(path)
    assert shape(restored['labels'][0]['geometry']).equals(shape(raw[0]['geometry']))
    assert settings(restored,'individual')['enabled']
    w.smooth_enabled.setChecked(False);save_project(w.project,path)
    data=json.loads(path.read_text(encoding='utf-8'))
    assert shape(data['labels'][0]['geometry']).equals(shape(raw[0]['geometry']))
    assert 'source_geometry' not in data['labels'][0]
    assert snapshot['smoothing']['individual']['enabled']  # No live preference mutation during a background write.


def test_draft_uses_same_smoothing_and_original_is_unchanged(smooth_workbench):
    w,app,wait,errors=smooth_workbench;w.draft={'geometry':mapping(box(200,200,260,260)),'points':[],'pending':False}
    original=w.draft['geometry'];w.refresh_labels();item=w.view.overlay_records['__draft']
    w.smooth_enabled.setChecked(True);settled(w,app)
    assert w.view.overlay_records['__draft'] is item and not shape(item.geometry_value).equals(shape(original))
    assert w.draft['geometry'] is original
    w.smooth_enabled.setChecked(False);app.processEvents()
    assert item.geometry_value is original


def test_crs_rows_and_export_text_are_centered(smooth_workbench):
    w,app,wait,errors=smooth_workbench
    w.refresh_info();values=[v.text() for v in w.image_info.values]
    assert values[1]=='EPSG:3857' and 'Pseudo-Mercator' in values[2]
    assert w.export_crs_input.alignment()==Qt.AlignmentFlag.AlignCenter
    assert w.export_kind.itemData(0,Qt.ItemDataRole.TextAlignmentRole)==Qt.AlignmentFlag.AlignCenter
    for row in range(w.labels_table.rowCount()):
        for column in range(2):assert w.labels_table.item(row,column).textAlignment()==Qt.AlignmentFlag.AlignCenter


def test_smoothing_does_not_expand_into_nodata(tmp_path):
    import rasterio
    from rasterio.features import rasterize
    from rasterio.transform import Affine
    from geoforma.raster import inspect_source,make_recipe
    g=Polygon([(10,10),(40,10),(40,20),(20,20),(20,40),(10,40)])
    a=rasterize([(mapping(g),100)],out_shape=(60,60),transform=Affine.identity(),dtype='uint8')
    path=tmp_path/'nodata.tif'
    with rasterio.open(path,'w',driver='GTiff',width=60,height=60,count=3,dtype='uint8',nodata=0,transform=Affine(1,0,10,0,-1,10)) as source:source.write(np.stack([a]*3))
    image=inspect_source(path);image['model_recipe']=make_recipe(image,[1,2,3])
    output=smooth_batch([label('a',g)],1,image)[0]
    assert shape(output['geometry']).difference(g).area<1e-9


@pytest.mark.parametrize('extension',['gpkg','shp','geojson'])
def test_vector_files_match_checkbox_state(smooth_workbench,raster_image,tmp_path,monkeypatch,extension):
    from PySide6.QtWidgets import QFileDialog
    from osgeo import ogr
    from rasterio.warp import transform_geom
    from shapely.affinity import affine_transform
    w,app,wait,errors=smooth_workbench;raster_image['id']='one'
    w.export_kind.setCurrentIndex(w.export_kind.findData('.'+extension))
    if extension=='shp':w.export_label_field_input.setText('class_val');w.commit_export_label_field()
    w.project['images']=[raster_image];w.image=raster_image;w.project['labels']=[label('a',box(20,20,80,80))];w.refresh_images();w.refresh_info();w.refresh_labels();wait()
    for enabled in (True,False):
        w.smooth_enabled.setChecked(enabled);settled(w,app)
        path=tmp_path/f'labels_{int(enabled)}.{extension}'
        monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *args:(str(path),''))
        w.export();wait();assert path.is_file() and not errors
        store=ogr.Open(str(path));feature=store.GetLayer().GetNextFeature();geometry=json.loads(feature.GetGeometryRef().ExportToJson());assert feature.GetField('smooth_px')==float(enabled);store=None
        if extension=='geojson':geometry=transform_geom('EPSG:4326','EPSG:3857',geometry)
        from rasterio.transform import Affine
        transform=~Affine(*raster_image['transform']);pixel=affine_transform(shape(geometry),[transform.a,transform.b,transform.d,transform.e,transform.c,transform.f])
        expected=shape(smooth_batch(w.project['labels'],1,raster_image)[0]['geometry']) if enabled else box(20,20,80,80)
        assert pixel.hausdorff_distance(expected)<1e-5


def test_reshape_target_and_other_labels_stay_smoothed(smooth_workbench):
    w,app,wait,errors=smooth_workbench;w.smooth_enabled.setChecked(True);settled(w,app)
    target=w.view.overlay_records['a'].geometry_value;other=w.view.overlay_records['b'].geometry_value
    w.select_label('a');w.begin_reshape();settled(w,app)
    assert w.view.overlay_records['a'].geometry_value is target
    assert not shape(target).equals(shape(w.project['labels'][0]['geometry']))
    assert w.view.overlay_records['b'].geometry_value is other
    w.cancel_reshape();settled(w,app)
    assert not shape(w.view.overlay_records['a'].geometry_value).equals(shape(w.project['labels'][0]['geometry']))
    assert not errors


def test_smoothing_keeps_panel_positions_and_input_focus(smooth_workbench):
    from test_stable_panels import rectangles
    w,app,wait,errors=smooth_workbench;w.resize(1024,700);app.processEvents();before=rectangles(w)
    w.smooth_enabled.setChecked(True);settled(w,app)
    w.smooth_value.setFocus();w.smooth_value.setValue(3);settled(w,app)
    assert rectangles(w)==before and w.smooth_value.hasFocus()
    assert w.smooth_value.parentWidget().rect().contains(w.smooth_value.geometry())
    w.smooth_enabled.setChecked(False);app.processEvents();assert rectangles(w)==before


def test_new_project_releases_previous_project_geometry_cache(smooth_workbench):
    w,app,wait,errors=smooth_workbench;w.smooth_enabled.setChecked(True);settled(w,app)
    assert w.smoother.last and w.smoother.cache
    w.new();settled(w,app)
    assert not w.project['labels'] and w.smoother.last is None and not w.smoother.cache and not errors


def test_inflight_work_cannot_publish_after_new_request_or_disabling(smooth_workbench):
    import threading
    w,app,wait,errors=smooth_workbench;queue=w.smoother;records=[label('test',box(0,0,10,10))]
    started=threading.Event();release=threading.Event();published=[]
    queue.updated.connect(lambda:published.append(queue.last[0]))
    def slow(task):
        started.set()
        while not release.wait(.002):task.check()
        return records
    queue.request('old',records,slow)
    deadline=time.monotonic()+3
    while not started.is_set():app.processEvents();QTest.qWait(2);assert time.monotonic()<deadline
    queue.request('new',records,lambda task:records);release.set();settled(w,app)
    assert published==['new'] and queue.last[0]=='new'
    started.clear();release.clear();queue.request('disabled',records,slow)
    deadline=time.monotonic()+3
    while not started.is_set():app.processEvents();QTest.qWait(2);assert time.monotonic()<deadline
    queue.stop();release.set();settled(w,app)
    assert published==['new'] and 'disabled' not in queue.cache


@pytest.mark.parametrize('value',[float('nan'),float('inf'),0,-1,6])
def test_invalid_strength_rejected(value):
    with pytest.raises(ValueError):smooth_geometry(mapping(box(0,0,20,20)),value)
