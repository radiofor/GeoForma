"""Saving a hole immediately refreshes every consumer of label records."""
import json

from osgeo import ogr
from PySide6.QtWidgets import QFileDialog
from rasterio.transform import Affine
from shapely.affinity import affine_transform
from shapely.geometry import Point,shape

from test_reshape import workbench,raster_image
from test_reshape_auto import wait
from test_smoothing import settled


def test_hole_updates_cached_lookup_canvas_export_and_history(workbench,monkeypatch):
    w,app,tmp=workbench
    w.smooth_enabled.setChecked(False);w.fill_holes.setChecked(False)
    w.refresh_labels();settled(w,app)
    before=w.current_labels()[0]
    w.set_tool('draw_polygon')
    for point in ((22,22),(28,22),(28,28),(22,28)):w.add_manual_vertex(*point)
    w.finish_manual_polygon();w.confirm();settled(w,app)
    current=w.current_labels()[0]
    assert current is not before and not shape(current['geometry']).covers(Point(25,25))
    assert not shape(w.view.overlay_records[current['id']].geometry_value).covers(Point(25,25))
    path=tmp/'hole.gpkg'
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *args:(str(path),''))
    w.export();wait(w,app)
    store=ogr.Open(str(path));assert store is not None
    layer=store.GetLayer();feature=layer.GetNextFeature()
    exported=shape(json.loads(feature.GetGeometryRef().ExportToJson()))
    transform=~Affine(*w.image['transform'])
    exported=affine_transform(exported,[transform.a,transform.b,transform.d,transform.e,transform.c,transform.f])
    feature=None;layer=None;store=None
    assert not exported.covers(Point(25,25))
    w.undo_label();assert shape(w.current_labels()[0]['geometry']).covers(Point(25,25))
    w.redo_label();assert not shape(w.current_labels()[0]['geometry']).covers(Point(25,25))
