"""Local reshape clipping must not union unrelated annotation geometry."""
import pytest
from shapely.geometry import box, mapping, shape

from geoforma import reshape


def intent():
    return {'original': mapping(box(0, 0, 10, 10)),
            'candidate': mapping(box(0, 0, 12, 10)),
            'window': [8, -1, 5, 12], 'stroke': [[10, 0], [12, 0], [12, 10], [10, 10]],
            'alternate': False}


def test_only_nearby_blockers_are_unioned_and_touching_remains_allowed(monkeypatch):
    near=box(11, 2, 13, 4);touching=box(12, 6, 14, 8);far=box(90, 90, 95, 95)
    observed=[];original=reshape.unary_union
    def capture(geometries):
        geometries=list(geometries);observed.extend(geometries)
        return original(geometries)
    monkeypatch.setattr(reshape,'unary_union',capture)
    result=shape(reshape.reshape_patch(intent(),{'width':100,'height':100},blockers=[mapping(g) for g in (near,touching,far)])['geometry'])
    assert result.area==118 and result.intersection(near).area==0
    assert result.boundary.intersects(touching.boundary)
    assert any(g.equals(near) for g in observed) and not any(g.equals(far) for g in observed)


def test_preexisting_overlap_still_fails_even_if_outside_addition():
    with pytest.raises(ValueError,match='已有标签存在重叠'):
        reshape.reshape_patch(intent(),{'width':100,'height':100},blockers=[mapping(box(2,2,4,4))])
