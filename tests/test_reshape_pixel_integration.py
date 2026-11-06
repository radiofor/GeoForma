"""Pixel-aligned model contours stay aligned throughout the UI workflow."""
import copy,time

import pytest
from shapely.geometry import LineString, Polygon, box, mapping, shape

from test_reshape import workbench, raster_image
from test_reshape_auto import wait
from test_smoothing import settled


def assert_pixel_edges(geometry):
    parts=geometry.geoms if geometry.geom_type=='MultiPolygon' else (geometry,)
    for part in parts:
        for ring in (part.exterior,*part.interiors):
            points=list(ring.coords)
            assert all(abs(x-round(x))<1e-9 and abs(y-round(y))<1e-9 for x,y in points)
            assert all(x1==x2 or y1==y2 for (x1,y1),(x2,y2) in zip(points,points[1:]))


@pytest.mark.parametrize('smooth',[False,True])
@pytest.mark.parametrize('mode',['point','box'])
def test_pixel_outline_remains_aligned_in_project_after_reshape(workbench,smooth,mode):
    from geoforma.storage import save_project,load_project
    w,app,tmp=workbench
    w.project['labels'][0]['source']='interactive'
    if mode=='box':w.project['labels'][0].update(points=[],box=[19.3,19.4,31.6,31.8])
    w.fill_holes.setChecked(False);w.smooth_enabled.setChecked(smooth);w.refresh_labels();settled(w,app)
    before=copy.deepcopy(w.project['labels'][0]['geometry'])
    w.begin_reshape(auto=True)
    for x,y in [[22,28],[23.2,34.3],[28,28]]:w.add_reshape_point(x,y)
    w.finish_reshape();wait(w,app)
    raw=shape(w.project['labels'][0]['geometry'])
    assert not raw.equals(shape(before)) and raw.is_valid
    assert_pixel_edges(raw)
    assert raw.intersection(box(0,0,100,29)).equals(shape(before).intersection(box(0,0,100,29)))
    w.begin_reshape(auto=True)
    for x,y in [[22,22],[22,15],[28,15],[28,22]]:w.add_reshape_point(x,y)
    w.finish_reshape();wait(w,app)
    current=shape(w.project['labels'][0]['geometry'])
    assert current.is_valid and not current.equals(raw)
    assert_pixel_edges(current)
    path=tmp/'aligned.gfm';save_project(w.project,path)
    assert shape(load_project(path)['labels'][0]['geometry']).equals(current)
    w.smooth_enabled.setChecked(False);settled(w,app)
    assert shape(w.view.overlay_records['target'].geometry_value).equals(current)
    w.undo_label();assert shape(w.project['labels'][0]['geometry']).equals(raw)
    w.undo_label();assert shape(w.project['labels'][0]['geometry']).equals(shape(before))


def test_manual_vector_preserves_unedited_diagonal(workbench):
    w,app,_=workbench
    label=w.project['labels'][0]
    original=Polygon([(20,20),(32,20),(30,30),(20,30)])
    label.update(source='manual_draw',geometry=mapping(original),editing_state='manual')
    w.fill_holes.setChecked(False);w.smooth_enabled.setChecked(False);w.refresh_labels();settled(w,app)
    w.begin_reshape(auto=True)
    for point in [[22,28],[23.2,34.3],[28,28]]:w.add_reshape_point(*point)
    w.finish_reshape();wait(w,app)
    result=shape(w.project['labels'][0]['geometry'])
    assert result.is_valid and not result.equals(original)
    assert result.boundary.covers(LineString([(32,20),(30,30)]))


@pytest.mark.parametrize('suffix',['gpkg','shp','geojson'])
def test_exported_raw_reshape_keeps_pixel_grid(workbench,monkeypatch,suffix):
    import json
    from osgeo import ogr
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QFileDialog
    from rasterio.transform import Affine
    from rasterio.warp import transform_geom
    from shapely.affinity import affine_transform
    w,app,tmp=workbench
    w.project['labels'][0]['source']='interactive'
    w.fill_holes.setChecked(False);w.smooth_enabled.setChecked(False);w.refresh_labels();settled(w,app)
    w.begin_reshape(auto=True)
    for point in [[22,28],[23.2,34.3],[28,28]]:w.add_reshape_point(*point)
    w.finish_reshape();wait(w,app)
    expected=shape(w.project['labels'][0]['geometry']);assert_pixel_edges(expected)
    path=tmp/('result.'+suffix)
    w.export_kind.setCurrentIndex(w.export_kind.findData('.'+suffix))
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *args:(str(path),''))
    w.export()
    # GDAL driver setup and reprojection can take longer on a busy Windows
    # machine; poll for completion without introducing any artificial delay.
    deadline=time.monotonic()+30
    while w.task:
        app.processEvents();QTest.qWait(2)
        assert time.monotonic()<deadline
    settled(w,app)
    store=ogr.Open(str(path));assert store is not None
    layer=store.GetLayer();feature=layer.GetNextFeature()
    geometry=json.loads(feature.GetGeometryRef().ExportToJson());feature=None;layer=None;store=None
    if suffix=='geojson':geometry=transform_geom('EPSG:4326','EPSG:3857',geometry)
    transform=~Affine(*w.image['transform'])
    actual=affine_transform(shape(geometry),[transform.a,transform.b,transform.d,transform.e,transform.c,transform.f])
    assert actual.hausdorff_distance(expected)<1e-5
