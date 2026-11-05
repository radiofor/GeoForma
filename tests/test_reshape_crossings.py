"""Repeated intersections, mixed additions/cuts and protected pixel geometry."""
import copy
import pytest
from shapely.geometry import Polygon,MultiPolygon,box,mapping,shape
from geoforma.reshape import reshape_intent,reshape_patch

STROKE=[[22,18],[22,22],[18,22],[18,26],[24,26],[24,32]]
ORIGINAL=box(20,20,30,30)
EXPECTED=ORIGINAL.union(box(18,22,20,26)).difference(box(20,20,22,22)).difference(box(20,26,24,30))


@pytest.mark.parametrize('reverse',[False,True])
@pytest.mark.parametrize('orientation',[False,True])
def test_repeated_crossings_both_extend_and_crop_one_ring(reverse,orientation):
    ring=list(ORIGINAL.exterior.coords)
    if orientation:ring.reverse()
    stroke=copy.deepcopy(STROKE)
    if reverse:stroke.reverse()
    result=reshape_patch(reshape_intent(mapping(Polygon(ring)),stroke),{'width':100,'height':100})
    assert shape(result['geometry']).equals(EXPECTED)
    assert result['added_pixels']==8 and result['removed_pixels']==20
    assert result['window'][2]*result['window'][3]<200


def test_multi_crossing_preserves_holes_and_other_parts():
    hole=box(27,23,29,25);sibling=box(60,60,70,70)
    geometry=MultiPolygon([ORIGINAL.difference(hole),sibling])
    result=reshape_patch(reshape_intent(mapping(geometry),STROKE),{'width':100,'height':100})
    assert shape(result['geometry']).equals(EXPECTED.difference(hole).union(sibling))


def test_reshape_interior_ring_preserves_other_holes():
    geometry=box(20,20,50,50).difference(box(25,25,35,35).union(box(42,25,46,29)))
    result=reshape_patch(reshape_intent(mapping(geometry),[[27,33],[27,38],[33,38],[33,33]]),{'width':100,'height':100})
    output=shape(result['geometry'])
    assert output.is_valid and len(output.interiors)==2
    assert any(Polygon(ring).equals(box(42,25,46,29)) for ring in output.interiors)
    assert output.area==geometry.area-18


def test_outer_stroke_may_cross_hole_and_open_it_to_exterior():
    geometry=box(20,20,40,40).difference(box(25,25,35,35))
    stroke=[[22,18],[22,28],[30,28],[30,42]]
    result=reshape_patch(reshape_intent(mapping(geometry),stroke),{'width':100,'height':100})
    output=shape(result['geometry'])
    assert output.is_valid and not output.equals(geometry)
    assert output.intersection(box(30,30,40,40)).equals(geometry.intersection(box(30,30,40,40)))


def test_one_stroke_can_edit_multiple_hole_boundaries():
    geometry=box(10,10,70,50).difference(box(20,20,30,40).union(box(45,20,55,40)))
    result=reshape_patch(reshape_intent(mapping(geometry),[[15,30],[60,30]]),{'width':100,'height':100})
    output=shape(result['geometry'])
    assert output.is_valid and not output.equals(geometry)
    assert not output.intersection(box(20,20,30,40)).equals(geometry.intersection(box(20,20,30,40)))
    assert not output.intersection(box(45,20,55,40)).equals(geometry.intersection(box(45,20,55,40)))


def test_shared_boundary_segment_can_lead_into_an_outside_edit():
    stroke=[[20,22],[20,24],[18,24],[18,28],[20,28]]
    result=reshape_patch(reshape_intent(mapping(ORIGINAL),stroke),{'width':100,'height':100})
    assert shape(result['geometry']).equals(ORIGINAL.union(box(18,24,20,28)))


def test_staircase_boundary_with_a_mixed_stroke_like_reported_image():
    geometry=Polygon([(176,167),(245,167),(245,190),(291,190),(291,258),(268,258),(268,305),(244,305),(244,328),(222,328),(222,305),(199,305),(199,282),(176,282),(176,258),(153,258),(153,236),(130,236),(130,213),(107,213),(107,190),(153,190),(153,167)])
    stroke=[[150,52],[163,175],[143,196],[95,204],[81,214],[79,232],[82,251],[148,237],[194,239],[213,253],[234,281],[232,332]]
    before=mapping(geometry);result=reshape_patch(reshape_intent(before,stroke),{'width':560,'height':520})
    final=shape(result['geometry'])
    assert final.is_valid and result['added_pixels']>0 and result['removed_pixels']>0
    assert all(x==int(x) and y==int(y) for x,y in final.exterior.coords)
    assert final.intersection(box(245,0,560,520)).equals(geometry.intersection(box(245,0,560,520)))
    assert mapping(geometry)==before
