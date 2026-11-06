"""Manual reshaping operates on the currently saved vector, not a pixel mask."""
import pytest
from shapely.geometry import Polygon,box,mapping,shape
from geoforma.reshape import reshape_intent,reshape_patch

IMAGE={'width':100,'height':100}


def edit(geometry,stroke,**kwargs):
    return shape(reshape_patch(reshape_intent(mapping(geometry),stroke),IMAGE,**kwargs)['geometry'])


def test_subpixel_expansion_is_not_discarded():
    original=box(20,20,30,30)
    final=edit(original,[[22,29.9],[22,30.2],[28,30.2],[28,29.9]])
    assert final.is_valid and final.area>original.area
    assert final.intersection(box(0,0,100,29)).equals(original.intersection(box(0,0,100,29)))


def test_new_boundary_keeps_unedited_hole_and_original_edges():
    hole=box(23.2,23.4,25.8,26.6)
    original=box(20,20,30,30).difference(hole)
    final=edit(original,[[21,29],[21,34],[29,34],[29,29]])
    assert final.is_valid and len(final.interiors)==1
    assert Polygon(final.interiors[0]).equals(hole)
    assert final.intersection(box(0,0,100,29)).equals(original.intersection(box(0,0,100,29)))
    assert final.covers(box(21,30,29,34))


def test_expansion_stops_at_other_label_without_changing_original():
    original=box(20,20,30,30);blocker=box(24,31,27,35)
    final=edit(original,[[21,29],[21,34],[29,34],[29,29]],blockers=[mapping(blocker)])
    assert final.is_valid and final.intersection(blocker).area==0
    assert final.covers(original)


@pytest.mark.parametrize('reverse',[False,True])
def test_narrow_repeated_crossings_repair_to_valid_polygon(reverse):
    original=Polygon([(10,10),(40,10),(40,36),(25,36),(25,38),(38,38),(38,40),(10,40)])
    stroke=[[18,42],[22,35],[27,37],[43,39]]
    if reverse:stroke.reverse()
    final=edit(original,stroke)
    assert final.is_valid and not final.equals(original)
    assert final.intersection(box(0,0,100,30)).equals(original.intersection(box(0,0,100,30)))
