import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtCore import Qt,QRectF,QPointF
from PySide6.QtWidgets import QApplication
from shapely.geometry import box,mapping
from geoforma.viewport import ImageView
from geoforma.rendering import scene_layers


def label(identifier,x,y):
    return {'id':identifier,'status':'confirmed','geometry':mapping(box(x,y,x+60,y+60)),
            '_bounds':[x,y,x+60,y+60]}


@pytest.fixture
def viewport(monkeypatch):
    app=QApplication.instance() or QApplication([]);writes=[]
    original=scene_layers.LabelItem
    class TrackedPathItem(original):
        def setPath(self,path):writes.append(self);super().setPath(path)
    monkeypatch.setattr(scene_layers,'LabelItem',TrackedPathItem)
    view=ImageView();view.resize(700,600);view.set_image(5000,5000);view.show();app.processEvents()
    def move(x,y,size=400):
        view.fitInView(QRectF(x,y,size,size),Qt.AspectRatioMode.KeepAspectRatio);app.processEvents()
    move(0,0)
    yield view,move,writes
    view.scene().clear();view.layers.reset();view.close();app.processEvents()


def test_pan_and_zoom_reuse_items_and_paths_prepared_for_the_entire_layer(viewport):
    view,move,writes=viewport;near=label('near',100,100);far=label('far',4000,4000);labels=[near,far]
    view.overlays(labels);first=view.overlay_records['near']
    assert set(view.overlay_records)=={'near','far'} and len(writes)==2 and writes.count(first)==1
    for _ in range(3):
        move(3900,3900);view.overlays(labels)
        assert view.overlay_records['near'] is first and first.scene() is view.scene()
        move(50,50,180);view.overlays(labels)
        assert view.overlay_records['near'] is first
    assert len(view.overlay_records)==2 and writes.count(first)==1 and len(writes)==2
    assert view.hit_label(view.mapFromScene(QPointF(130,130)))=='near'


def test_path_cache_eviction_does_not_rebuild_retained_scene_geometry(viewport):
    view,move,writes=viewport;near=label('near',100,100);view.overlays([near]);first=view.overlay_records['near']
    view.path_cache.max_entries=16
    for i in range(24):view.cached_path(mapping(box(i,200,i+1,201)))
    assert id(near['geometry']) not in view.path_cache
    move(3900,3900);view.overlays([near]);move(0,0);view.overlays([near])
    assert view.overlay_records['near'] is first and writes==[first]


def test_geometry_edit_updates_existing_item_and_deletion_removes_it(viewport):
    view,move,writes=viewport;near=label('near',100,100);far=label('far',4000,4000)
    view.overlays([near,far]);first=view.overlay_records['near'];move(3900,3900)
    edited=label('near',120,120);view.overlays([edited,far])
    assert view.overlay_records['near'] is first and writes.count(first)==2
    move(0,0);view.overlays([edited,far]);assert writes.count(first)==2
    assert view.hit_label(view.mapFromScene(QPointF(150,150)))=='near'
    view.overlays([far]);assert 'near' not in view.overlay_records and first.scene() is None


def test_raw_visibility_and_data_switch_do_not_resurrect_old_items(viewport):
    view,move,writes=viewport;near=label('near',100,100);view.overlays([near]);first=view.overlay_records['near']
    view.set_overlay_visibility(False);move(3900,3900);view.overlays([near]);move(0,0);view.overlays([near])
    assert not first.isVisible() and view.hit_label(view.mapFromScene(QPointF(130,130))) is None
    view.set_overlay_visibility(True);assert first.isVisible() and writes==[first]
    view.overlays([]);assert not view.overlay_records  # Mode/candidate-set change.
    view.overlays([near]);assert view.overlay_records['near'] is not first
    view.set_image(2000,2000);assert not view.overlay_records and id(near['geometry']) in view.path_cache


def test_returning_to_an_image_reuses_its_cached_geometry_path(viewport,monkeypatch):
    view,move,writes=viewport;near=label('near',100,100);calls=[];original=scene_layers.geometry_path
    def track(geometry):calls.append(geometry);return original(geometry)
    monkeypatch.setattr(scene_layers,'geometry_path',track)
    view.overlays([near]);view.set_image(2000,2000);view.overlays([])
    view.set_image(5000,5000);view.overlays([near])
    assert calls==[near['geometry']] and id(near['geometry']) in view.path_cache
