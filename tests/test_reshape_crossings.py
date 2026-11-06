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
    assert shape(result['geometry']).symmetric_difference(EXPECTED).area<1
    assert result['added_pixels']==8 and result['removed_pixels']==20
    assert result['window'][2]*result['window'][3]<200


def test_multi_crossing_preserves_holes_and_other_parts():
    hole=box(27,23,29,25);sibling=box(60,60,70,70)
    geometry=MultiPolygon([ORIGINAL.difference(hole),sibling])
    result=reshape_patch(reshape_intent(mapping(geometry),STROKE),{'width':100,'height':100})
    output=shape(result['geometry'])
    assert output.symmetric_difference(EXPECTED.difference(hole).union(sibling)).area<1
    assert output.intersection(sibling).equals(sibling) and output.intersection(hole).area==0


def test_reshape_interior_ring_preserves_other_holes():
    geometry=box(20,20,50,50).difference(box(25,25,35,35).union(box(42,25,46,29)))
    result=reshape_patch(reshape_intent(mapping(geometry),[[27,33],[27,38],[33,38],[33,33]]),{'width':100,'height':100})
    output=shape(result['geometry'])
    assert output.is_valid and len(output.interiors)==2
    assert any(Polygon(ring).equals(box(42,25,46,29)) for ring in output.interiors)
    assert output.area==pytest.approx(geometry.area-18,abs=.5)


def test_outer_stroke_may_cross_hole_and_open_it_to_exterior():
    geometry=box(20,20,40,40).difference(box(25,25,35,35))
    stroke=[[22,18],[22,28],[30,28],[30,42]]
    result=reshape_patch(reshape_intent(mapping(geometry),stroke),{'width':100,'height':100})
    output=shape(result['geometry'])
    assert output.is_valid and not output.equals(geometry)
    assert output.intersection(box(30,30,40,40)).equals(geometry.intersection(box(30,30,40,40)))


def test_removed_fractional_hole_does_not_reappear_after_a_later_expansion():
    hole=box(35.2,20.2,40.8,30.8);sibling=box(60,60,70,70)
    original=MultiPolygon([box(10,10,50,50).difference(hole),sibling])
    first=shape(reshape_patch(reshape_intent(mapping(original),[[30,5],[30,55]],True),{'width':100,'height':100})['geometry'])
    parts=list(first.geoms)
    assert len(parts)==2 and any(part.equals(sibling) for part in parts)
    left=next(part for part in parts if not part.equals(sibling))
    assert left.equals(box(10,10,30,50))
    second=shape(reshape_patch(reshape_intent(mapping(left),[[29,12],[45,12],[45,48],[29,48]]),
                               {'width':100,'height':100},blockers=[mapping(sibling)])['geometry'])
    assert second.is_valid and second.intersection(hole).equals(hole)


@pytest.mark.parametrize('cut',[34.9,39.4])
def test_connected_fractional_hole_remnants_are_removed_without_changing_other_holes(cut):
    removed_hole=box(35.2,20.2,40.8,30.8);kept_hole=box(17.3,17.3,21.7,21.7)
    original=box(10,10,50,50).difference(removed_hole.union(kept_hole))
    first=shape(reshape_patch(reshape_intent(mapping(original),[[cut,5],[cut,55]]),{'width':100,'height':100})['geometry'])
    assert first.is_valid and len(first.interiors)==1
    assert Polygon(first.interiors[0]).equals(kept_hole)
    assert first.intersection(box(0,0,25,60)).equals(original.intersection(box(0,0,25,60)))
    # The next edit must use the first result, not recover the removed hole.
    stroke=[[cut-1,12],[46,12],[46,48],[cut-1,48]]
    second=shape(reshape_patch(reshape_intent(mapping(first),stroke),{'width':100,'height':100})['geometry'])
    assert second.is_valid and second.intersection(removed_hole).equals(removed_hole)
    assert len(second.interiors)==1 and Polygon(second.interiors[0]).equals(kept_hole)


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
    assert shape(result['geometry']).symmetric_difference(ORIGINAL.union(box(18,24,20,28))).area<1


def test_staircase_boundary_with_a_mixed_stroke_like_reported_image():
    geometry=Polygon([(176,167),(245,167),(245,190),(291,190),(291,258),(268,258),(268,305),(244,305),(244,328),(222,328),(222,305),(199,305),(199,282),(176,282),(176,258),(153,258),(153,236),(130,236),(130,213),(107,213),(107,190),(153,190),(153,167)])
    stroke=[[150,52],[163,175],[143,196],[95,204],[81,214],[79,232],[82,251],[148,237],[194,239],[213,253],[234,281],[232,332]]
    before=mapping(geometry);result=reshape_patch(reshape_intent(before,stroke),{'width':560,'height':520})
    final=shape(result['geometry'])
    assert final.is_valid and result['added_pixels']>0 and result['removed_pixels']>0
    assert final.intersection(box(245,0,560,520)).equals(geometry.intersection(box(245,0,560,520)))
    assert mapping(geometry)==before
