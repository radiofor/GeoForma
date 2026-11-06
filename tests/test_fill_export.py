"""Export uses the same reversible hole presentation as the canvas."""
import json
import pytest
from osgeo import ogr
from PySide6.QtWidgets import QFileDialog
from rasterio.transform import Affine
from rasterio.warp import transform_geom
from shapely.affinity import affine_transform
from shapely.geometry import Point,box,mapping,shape

from test_reshape import raster_image
from test_workbench import workbench


@pytest.mark.parametrize('suffix',['gpkg','shp','geojson'])
@pytest.mark.parametrize('filled',[False,True])
@pytest.mark.parametrize('smooth',[False,True])
def test_export_tracks_fill_option_without_mutating_labels(workbench,raster_image,monkeypatch,suffix,filled,smooth):
    w,app,wait,errors=workbench;image=raster_image;image['id']='one'
    w.project['images']=[image]
    outer=box(20,20,80,80).difference(box(30,30,45,45));inner=box(35,35,40,40)
    w.project['labels']=[dict(id=name,image_id='one',class_id=1,status='confirmed',geometry=mapping(geom))
                         for name,geom in (('outer',outer),('inner',inner))]
    w.refresh_images();w.images.setCurrentRow(0);w.refresh_labels();wait()
    w.smooth_enabled.setChecked(smooth);w.fill_holes.setChecked(filled)
    w.export_kind.setCurrentIndex(w.export_kind.findData('.'+suffix))
    path=w.project_path.parent/f'{suffix}_{filled}_{smooth}.{suffix}'
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *args:(str(path),''))
    w.export();wait();assert path.is_file() and not errors
    store=ogr.Open(str(path));layer=store.GetLayer();geometries={}
    transform=~Affine(*image['transform'])
    for feature in layer:
        geometry=json.loads(feature.GetGeometryRef().ExportToJson())
        if suffix=='geojson':geometry=transform_geom('EPSG:4326','EPSG:3857',geometry)
        geometries[feature.GetField('label_id')]=affine_transform(shape(geometry),[transform.a,transform.b,transform.d,transform.e,transform.c,transform.f])
    store=None
    assert geometries['outer'].covers(Point(32,32)) is filled
    assert geometries['outer'].intersection(geometries['inner']).area<1e-8
    assert shape(w.project['labels'][0]['geometry']).equals(outer)
    from geoforma.label_presentation import presentation_batch
    expected=presentation_batch(w.project['labels'],filled,{'enabled':smooth,'value':1.0},image)
    for label in expected:assert geometries[label['id']].hausdorff_distance(shape(label['geometry']))<1e-5
