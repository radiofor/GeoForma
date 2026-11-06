"""Synthetic invalid reshape outputs are repaired as polygonal geometry."""
import pytest
from shapely.geometry import GeometryCollection,LineString,MultiPolygon,Polygon,box,mapping
from geoforma.reshape_validity import repair_reshape_geometry


def test_self_intersecting_result_recovers_all_polygon_components():
    bow=Polygon([(0,0),(4,4),(0,4),(4,0),(0,0)])
    result=repair_reshape_geometry(mapping(bow))
    assert result.is_valid and result.geom_type=='MultiPolygon'
    assert len(result.geoms)==2 and result.area==8


def test_collection_preserves_polygonal_parts_but_discards_lines():
    source=GeometryCollection([box(0,0,2,2),LineString([(8,8),(9,9)]),box(4,4,6,6)])
    result=repair_reshape_geometry(source)
    assert result.is_valid and result.equals(MultiPolygon([box(0,0,2,2),box(4,4,6,6)]))


@pytest.mark.parametrize('source',[GeometryCollection(),LineString([(0,0),(1,1)]),
                                  Polygon([(0,0),(1,0),(2,0),(0,0)])])
def test_nonpolygonal_or_empty_result_is_rejected(source):
    with pytest.raises(ValueError,match='没有可保留的多边形'):
        repair_reshape_geometry(source)


def test_valid_result_is_reused_with_holes_unchanged():
    source=box(0,0,10,10).difference(box(3,3,5,5))
    result=repair_reshape_geometry(source)
    assert result is source and len(result.interiors)==1
