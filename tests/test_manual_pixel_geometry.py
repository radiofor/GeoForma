"""Hand-drawn geometry shares the model's source pixel contours."""
import copy
from shapely.geometry import box,mapping,shape
from shapely.ops import unary_union

from geoforma.manual_holes import create_hole
from geoforma.pixel_geometry import pixel_contour
from test_reshape import workbench,raster_image


def assert_grid(geometry):
    pieces=geometry.geoms if geometry.geom_type=='MultiPolygon' else (geometry,)
    for part in pieces:
        for ring in (part.exterior,*part.interiors):
            for a,b in zip(ring.coords,list(ring.coords)[1:]):
                assert a[0]==b[0] or a[1]==b[1]
                assert all(abs(value-round(value))<1e-9 for value in (*a,*b))


def test_model_mask_contours_match_previous_algorithm_for_offsets_and_clipping():
    import numpy as np
    from rasterio.features import shapes
    from rasterio.transform import Affine
    from geoforma.backend import mask_geometry,SamBackend
    from geoforma.sam2_backend import Sam2Backend
    masks=[np.zeros((6,7),dtype=bool),np.eye(6,7,dtype=bool),
           np.array([[1,1,0,1],[1,0,0,1],[1,1,1,1]],dtype='uint8')]
    assert Sam2Backend.predict is SamBackend.predict
    for mask in masks:
        for window,image in (([0,0,7,6],{'width':10,'height':10}),([8,7,7,6],{'width':10,'height':10}),([-2,-1,7,6],{'width':10,'height':10})):
            pieces=[shape(g) for g,_ in shapes(mask.astype('uint8'),mask=mask.astype(bool),transform=Affine.translation(window[0],window[1]))]
            old=unary_union(pieces).intersection(box(0,0,image['width'],image['height'])) if pieces else None
            actual=mask_geometry(mask,window,image)
            assert (actual is None)==(old is None or old.area==0)
            if actual:
                assert shape(actual).geom_type in ('Polygon','MultiPolygon')
                assert shape(actual).symmetric_difference(old).area==0


def test_mask_clipping_discards_zero_area_boundary_contacts():
    import numpy as np
    from geoforma.pixel_geometry import mask_geometry
    image={'width':5,'height':5}
    assert mask_geometry(np.array([[1]],dtype='uint8'),[-1,0,1,1],image) is None
    result=mask_geometry(np.array([[1,0,1]],dtype='uint8'),[-1,0,3,1],image)
    assert shape(result).equals(box(1,0,2,1))


def disconnected_source():
    return unary_union([box(22,22,25,25),box(27,22,30,25),box(25,23.1,27,23.2)])


def test_multiple_pixel_components_inside_label_create_holes():
    parent=box(20,20,40,40);source=disconnected_source()
    pixels=shape(pixel_contour(mapping(source),{'width':100,'height':100}))
    assert pixels.geom_type=='MultiPolygon' and len(pixels.geoms)==2
    label={'id':'saved','status':'confirmed','geometry':mapping(parent)}
    updated=create_hole(mapping(pixels),[label])
    result=shape(updated['geometry'])
    assert result.is_valid and len(result.interiors)==2 and result.area==parent.area-pixels.area
    assert shape(label['geometry']).equals(parent)


def test_drawn_diagonal_becomes_pixel_contour_and_undoable_label(workbench):
    w,app,_=workbench;w.single_polygon.setChecked(False);w.fill_holes.setChecked(False)
    before=copy.deepcopy(w.project['labels']);w.set_tool('draw_polygon')
    for point in ((45,45),(60,48),(56,61),(44,57)):w.add_manual_vertex(*point)
    w.finish_manual_polygon();result=shape(w.draft['geometry'])
    assert result.is_valid;assert_grid(result)
    w.confirm();assert len(w.project['labels'])==len(before)+1
    assert_grid(shape(w.project['labels'][-1]['geometry']))
    w.undo_context();assert w.project['labels']==before


def test_small_draw_keeps_vertices_when_no_pixel_is_covered(workbench):
    w,app,_=workbench;w.set_tool('draw_polygon')
    for point in ((45.01,45.01),(45.1,45.01),(45.01,45.1)):w.add_manual_vertex(*point)
    vertices=copy.deepcopy(w.draft['manual_vertices']);w.finish_manual_polygon()
    assert w.draft['manual_vertices']==vertices and not w.draft.get('geometry')
    assert '像元' in w.statusBar()._error_toast.label.text()


def _dumbbell(x,y):
    return [(x,y),(x+3,y),(x+3,y+1.1),(x+5,y+1.1),(x+5,y),
            (x+8,y),(x+8,y+3),(x+5,y+3),(x+5,y+1.2),
            (x+3,y+1.2),(x+3,y+3),(x,y+3)]


def test_disconnected_manual_result_creates_independent_labels(workbench):
    w,app,_=workbench;w.single_polygon.setChecked(False);w.fill_holes.setChecked(False)
    before=copy.deepcopy(w.project['labels']);w.set_tool('draw_polygon')
    for point in _dumbbell(45,45):w.add_manual_vertex(*point)
    w.finish_manual_polygon();assert shape(w.draft['geometry']).geom_type=='MultiPolygon'
    assert len(w.draft_labels())==2
    w.confirm();created=[l for l in w.project['labels'] if l.get('source')=='manual_draw']
    assert len(created)==2 and all(shape(l['geometry']).geom_type=='Polygon' for l in created)
    w.undo_context();assert w.project['labels']==before


def test_disconnected_manual_result_creates_multiple_holes(workbench):
    w,app,_=workbench;w.single_polygon.setChecked(False);w.fill_holes.setChecked(False)
    before=copy.deepcopy(w.project['labels']);w.set_tool('draw_polygon')
    for point in _dumbbell(21,22):w.add_manual_vertex(*point)
    w.finish_manual_polygon();assert shape(w.draft['geometry']).geom_type=='MultiPolygon'
    w.confirm();assert len(w.project['labels'])==1
    assert len(shape(w.project['labels'][0]['geometry']).interiors)==2
    w.undo_context();assert w.project['labels']==before


def test_large_manual_contour_runs_in_worker_and_cancel_keeps_vertices(workbench,monkeypatch):
    import threading,time
    from PySide6.QtCore import QTimer
    from PySide6.QtTest import QTest
    from geoforma import pixel_geometry
    w,app,_=workbench;w.image['width']=1000;w.image['height']=1000;w.set_tool('draw_polygon')
    for point in ((10,10),(700,10),(700,700),(10,700)):w.add_manual_vertex(*point)
    vertices=copy.deepcopy(w.draft['manual_vertices']);started=threading.Event();release=threading.Event()
    original=pixel_geometry.pixel_contour
    def delayed(geometry,image,task):
        started.set()
        while not release.wait(.005):task.check()
        return original(geometry,image,task)
    monkeypatch.setattr(pixel_geometry,'pixel_contour',delayed)
    ticks=[];timer=QTimer();timer.setInterval(5);timer.timeout.connect(lambda:ticks.append(1));timer.start()
    try:
        w.finish_manual_polygon();deadline=time.monotonic()+5
        while not started.is_set():app.processEvents();QTest.qWait(5);assert time.monotonic()<deadline
        QTest.qWait(50);app.processEvents();assert ticks and w.task is not None
        w.cancel();release.set()
        while w.task is not None:app.processEvents();QTest.qWait(5);assert time.monotonic()<deadline
        assert w.draft['manual_vertices']==vertices and not w.draft.get('geometry')
    finally:release.set();timer.stop()


def test_stale_large_contour_cannot_replace_new_image_draft(workbench,monkeypatch):
    import threading,time
    from PySide6.QtTest import QTest
    from geoforma import pixel_geometry
    w,app,_=workbench;w.image['width']=1000;w.image['height']=1000;w.set_tool('draw_polygon')
    for point in ((10,10),(700,10),(700,700),(10,700)):w.add_manual_vertex(*point)
    vertices=copy.deepcopy(w.draft['manual_vertices']);other=copy.deepcopy(w.image);other['id']='other'
    w.project['images'].append(other);monkeypatch.setattr(w,'request_render',lambda *args:None)
    started=threading.Event();release=threading.Event()
    def delayed(geometry,image,task):
        started.set()
        while not release.wait(.005):task.check()
        return mapping(box(10,10,700,700))
    monkeypatch.setattr(pixel_geometry,'pixel_contour',delayed)
    try:
        w.finish_manual_polygon();deadline=time.monotonic()+5
        while not started.is_set():app.processEvents();QTest.qWait(5);assert time.monotonic()<deadline
        w._activate_image(1);release.set()
        while w.task is not None:app.processEvents();QTest.qWait(5);assert time.monotonic()<deadline
        assert w.image is other and not w.draft.get('geometry')
        w._activate_image(0);assert w.draft['manual_vertices']==vertices
    finally:release.set()


def test_large_manual_contour_failure_preserves_vertices_and_reports_failure(workbench,monkeypatch):
    import time
    from PySide6.QtTest import QTest
    from geoforma import pixel_geometry
    from geoforma.task_status import task_name
    w,app,_=workbench;w.image['width']=1000;w.image['height']=1000;w.set_tool('draw_polygon')
    for point in ((10,10),(700,10),(700,700),(10,700)):w.add_manual_vertex(*point)
    vertices=copy.deepcopy(w.draft['manual_vertices'])
    def fail(*args):raise ValueError('无法生成像元轮廓')
    monkeypatch.setattr(pixel_geometry,'pixel_contour',fail)
    w.finish_manual_polygon();deadline=time.monotonic()+5
    while w.task is not None:app.processEvents();QTest.qWait(5);assert time.monotonic()<deadline
    assert task_name('manual_polygon')=='生成多边形'
    assert w.progress.phase=='failed' and w.draft['manual_vertices']==vertices
