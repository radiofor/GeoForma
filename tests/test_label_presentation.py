"""Filling is non-destructive, deterministic, and shared with smoothing."""
import copy
import pytest
from shapely.geometry import box,mapping,shape
from geoforma.hole_filling import fill_label_holes,has_holes
from geoforma.label_presentation import presentation_batch


def record(identifier,geometry,image='image'):
    return {'id':identifier,'image_id':image,'status':'confirmed','class_id':1,'geometry':mapping(geometry)}


def test_nested_holes_are_filled_without_overwriting_other_labels():
    outer=box(0,0,30,30).difference(box(5,5,25,25))
    inner=box(8,8,22,22).difference(box(12,12,18,18))
    island=box(14,14,16,16)
    records=[record('outer',outer),record('inner',inner),record('island',island)]
    before=copy.deepcopy(records);filled=fill_label_holes(records)
    assert records==before and [row['id'] for row in filled]==['outer','inner','island']
    shapes=[shape(row['geometry']) for row in filled]
    assert all(shapes[i].intersection(shapes[j]).area==0 for i in range(3) for j in range(i+1,3))
    assert all(shapes[i].covers(shape(records[i]['geometry'])) for i in range(3))
    assert shapes[1].covers(box(12,12,14,14)) and not shapes[0].covers(box(12,12,14,14))
    assert shapes[2].equals(island)


def test_single_label_filling_and_occupied_hole():
    source=record('a',box(0,0,10,10).difference(box(2,2,8,8)))
    before=copy.deepcopy(source)
    assert shape(fill_label_holes([source])[0]['geometry']).equals(box(0,0,10,10))
    blocker=record('b',box(4,4,6,6))
    filled=fill_label_holes([source,blocker])
    assert shape(filled[0]['geometry']).equals(box(0,0,10,10).difference(box(4,4,6,6)))
    assert source==before and filled[1] is blocker


def test_other_image_does_not_block_and_missing_image_id_uses_current_context():
    source=box(0,0,10,10).difference(box(3,3,7,7))
    records=[record('a',source,'first'),record('b',box(4,4,6,6),'second')]
    assert shape(fill_label_holes(records)[0]['geometry']).equals(box(0,0,10,10))
    records[1].pop('image_id')
    assert not shape(fill_label_holes(records)[0]['geometry']).intersects(box(4.1,4.1,5.9,5.9))


def test_presentation_toggle_does_not_change_source_and_supports_smoothing():
    source=record('a',box(0,0,20,20).difference(box(7,7,13,13)))
    before=copy.deepcopy(source);off={'enabled':False,'value':1};on={'enabled':True,'value':1}
    assert len(shape(presentation_batch([source],False,off)[0]['geometry']).interiors)==1
    assert len(shape(presentation_batch([source],True,off)[0]['geometry']).interiors)==0
    assert len(shape(presentation_batch([source],True,on,{'width':30,'height':30})[0]['geometry']).interiors)==0
    assert len(shape(presentation_batch([source],False,on,{'width':30,'height':30})[0]['geometry']).interiors)==1
    assert source==before


def test_fill_checks_cancellation_and_reuses_geometry_without_holes():
    records=[record('a',box(0,0,10,10))]
    class Cancel:
        def check(self):raise RuntimeError('cancelled')
    with pytest.raises(RuntimeError,match='cancelled'):fill_label_holes(records,Cancel())
    assert fill_label_holes(records)[0] is records[0]


def test_hole_check_supports_polygon_multi_and_empty():
    from shapely.geometry import MultiPolygon
    plain=box(0,0,10,10);donut=plain.difference(box(3,3,7,7))
    assert not has_holes(None) and not has_holes(mapping(plain))
    assert has_holes(mapping(donut)) and has_holes(mapping(MultiPolygon([donut,box(20,20,21,21)])))
