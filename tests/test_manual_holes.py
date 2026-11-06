"""Manual holes preserve the saved label identity and normal undo history."""
import copy
from shapely.geometry import Point,box,mapping,shape
from geoforma.manual_holes import create_hole
from test_reshape import workbench,raster_image


def test_containment_is_strict_and_respects_existing_holes():
    outer=box(0,0,20,20).difference(box(4,4,6,6))
    label={'id':'a','status':'confirmed','geometry':mapping(outer)}
    result=create_hole(mapping(box(10,10,12,12)),[label])
    assert len(shape(result['geometry']).interiors)==2
    assert not shape(result['geometry']).covers(Point(11,11))
    assert create_hole(mapping(box(0,10,3,12)),[label]) is None
    assert create_hole(mapping(box(3,3,7,7)),[label]) is None
    assert create_hole(mapping(box(21,21,22,22)),[label]) is None
    assert shape(label['geometry']).equals(outer)


def test_manual_hole_save_undo_redo(workbench):
    w,app,_=workbench;w.fill_holes.setChecked(False)
    before=copy.deepcopy(w.project['labels'][0]);w.set_tool('draw_polygon')
    for point in ((22,22),(28,22),(28,28),(22,28)):w.add_manual_vertex(*point)
    w.finish_manual_polygon();assert w.draft.get('geometry')
    w.confirm();assert not w.draft and len(w.project['labels'])==1
    result=w.project['labels'][0]
    assert result['id']==before['id'] and result['class_id']==before['class_id']
    assert result['status']=='confirmed' and result['editing_state']=='manual'
    assert not shape(result['geometry']).covers(Point(25,25))
    assert not w.fill_holes.isChecked()
    w.undo_context();assert shape(w.project['labels'][0]['geometry']).equals(shape(before['geometry']))
    w.redo_context();assert not shape(w.project['labels'][0]['geometry']).covers(Point(25,25))
    from geoforma.project_validation import validate_project
    validate_project(w.project)


def test_fill_mode_blocks_hole_without_changing_existing_label(workbench):
    w,app,_=workbench;w.fill_holes.setChecked(True)
    before=copy.deepcopy(w.project['labels']);w.set_tool('draw_polygon')
    for point in ((22,22),(28,22),(28,28),(22,28)):w.add_manual_vertex(*point)
    w.finish_manual_polygon();draft=copy.deepcopy(w.draft)
    w.confirm()
    assert w.project['labels']==before and w.draft==draft
    assert '填充洞' in w.statusBar().currentMessage()
    w.fill_holes.setChecked(False);w.confirm()
    assert len(w.project['labels'])==1 and not w.draft
    assert not shape(w.project['labels'][0]['geometry']).covers(Point(25,25))
    w.undo_context();assert w.project['labels']==before
