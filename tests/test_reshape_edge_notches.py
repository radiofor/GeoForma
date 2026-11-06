"""Editing a former border gap must follow the current polygon."""
import pytest
from shapely.geometry import box,mapping,shape
from shapely.ops import unary_union
from geoforma.reshape import reshape_intent,reshape_patch


@pytest.mark.parametrize('offset',[0,.2])
def test_redraw_cut_notches_without_filling_untouched_notch(offset):
    image={'width':100,'height':100}
    gaps=[box(20,y+offset,25,y+5+offset) for y in (20,40,60)]
    original=box(20,10,60,90).difference(unary_union(gaps))
    cut=[[19,15],[30+offset,15],[30+offset,55],[19,55]]
    first=shape(reshape_patch(reshape_intent(mapping(original),cut),image)['geometry'])
    assert first.is_valid and all(first.intersection(gap).area==0 for gap in gaps)
    assert first.intersection(box(20,18,29,52)).area==0
    stroke=[[31,18],[18,18],[18,52],[31,52]]
    final=shape(reshape_patch(reshape_intent(mapping(first),stroke),image)['geometry'])
    assert final.is_valid and all(final.covers(gap) for gap in gaps[:2])
    assert final.intersection(gaps[2]).area==0
    assert final.intersection(box(18,58,60,90)).equals(original.intersection(box(18,58,60,90)))


@pytest.mark.parametrize('offset',[0,.3])
def test_cut_all_three_notches_then_restore_every_region(offset):
    image={'width':100,'height':100}
    gaps=[box(20,y+offset,25,y+5+offset) for y in (20,40,60)]
    original=box(20,10,60,90).difference(unary_union(gaps))
    first=shape(reshape_patch(reshape_intent(mapping(original),[[30+offset,5],[30+offset,95]]),image)['geometry'])
    assert first.is_valid and first.bounds[0]>=30
    final=shape(reshape_patch(reshape_intent(mapping(first),[[32,15],[18,15],[18,85],[32,85]]),image)['geometry'])
    assert final.is_valid and all(final.covers(gap) for gap in gaps)
