"""Touching boundaries must not trigger expensive polygon clipping."""
from shapely.geometry import box, mapping, shape
from shapely.geometry.base import BaseGeometry
from geoforma import label_index


def label(identifier, geometry):
    return {'id': identifier, 'status': 'confirmed', 'geometry': mapping(geometry)}


def test_touching_labels_and_draft_do_not_trigger_clipping(monkeypatch):
    labels = [label(str(i), box(i, 0, i + 1, 1)) for i in range(20)]
    def unexpected(*args, **kwargs):
        raise AssertionError('touching polygons do not need clipping')
    monkeypatch.setattr(label_index, 'unary_union', unexpected)
    index = label_index.LabelIndex(labels)
    monkeypatch.setattr(BaseGeometry, 'difference', unexpected)
    result = index.visible({'geometry': mapping(box(20, 0, 21, 1))})
    assert len(result) == len(labels)
    assert all(item['geometry'] is original['geometry'] for item, original in zip(result, labels))


def test_overlaps_and_containment_still_clip_in_order():
    labels = [label('a', box(0, 0, 4, 4)), label('b', box(2, 0, 6, 4)),
              label('c', box(3, 1, 4, 2))]
    result = label_index.LabelIndex(labels).visible()
    assert [item['id'] for item in result] == ['a', 'b', 'c']
    assert [shape(item['geometry']).area for item in result] == [8, 15, 1]
