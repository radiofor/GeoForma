"""Pixel contours retain staircase boundaries after local reshape."""
import pytest
from shapely.geometry import LineString,box,mapping,shape
from geoforma.reshape import reshape_intent,reshape_patch


def _axis_aligned(polygon):
    for ring in [polygon.exterior,*polygon.interiors]:
        for a,b in zip(ring.coords,list(ring.coords)[1:]):
            assert abs(a[0]-b[0])<1e-9 or abs(a[1]-b[1])<1e-9


def test_diagonal_stroke_yields_pixel_steps_and_preserves_existing_hole():
    original=box(10,10,30,30).difference(box(15,15,18,18))
    stroke=[[22,29],[25,33],[29,31],[31,27]]
    intent=reshape_intent(mapping(original),stroke)
    result=shape(reshape_patch(intent,{'width':50,'height':50},pixel_grid=True)['geometry'])
    assert result.is_valid and len(result.interiors)==1
    assert result.interiors[0].equals(original.interiors[0])
    assert result.boundary.covers(LineString([(10,10),(30,10),(30,20)]))
    assert not result.equals(original)
    _axis_aligned(result)


def test_non_grid_blocker_is_not_cut_into_partial_pixels():
    original=box(10,10,20,20)
    stroke=[[12,19],[14,24],[19,22],[21,18]]
    blocker=box(16.2,20.3,17.4,21.2)
    intent=reshape_intent(mapping(original),stroke)
    result=shape(reshape_patch(intent,{'width':50,'height':50},blockers=[mapping(blocker)],pixel_grid=True)['geometry'])
    assert result.is_valid and result.intersection(blocker).area==0
    _axis_aligned(result)


def test_only_blockers_near_added_pixels_are_rasterized(monkeypatch):
    from geoforma import reshape
    original=box(10,10,20,20);near=box(16.8,20.1,17.2,20.9);far=box(40,40,45,45)
    intent=reshape_intent(mapping(original),[[12,19],[14,24],[19,22],[21,18]])
    calls=[];real=reshape.rasterize
    def record(items,*args,**kwargs):
        items=list(items)
        if kwargs.get('all_touched'):calls.extend(shape(geometry) for geometry,_ in items)
        return real(items,*args,**kwargs)
    monkeypatch.setattr(reshape,'rasterize',record)
    result=shape(reshape_patch(intent,{'width':50,'height':50},blockers=[mapping(near),mapping(far)],pixel_grid=True)['geometry'])
    assert any(g.equals(near) for g in calls) and not any(g.equals(far) for g in calls)
    assert result.intersection(near).area==0 and result.is_valid
    _axis_aligned(result)


def test_subpixel_edit_without_changed_pixels_is_reported():
    intent=reshape_intent(mapping(box(10,10,20,20)),[[11,15],[9.8,15],[9.8,17],[11,17]])
    with pytest.raises(ValueError,match='未改变任何像元'):
        reshape_patch(intent,{'width':50,'height':50},pixel_grid=True)


def test_cut_off_hole_does_not_reappear_when_area_is_added_back():
    original=box(10,10,30,30).difference(box(12,18,14,20))
    cut=reshape_intent(mapping(original),[[15,9],[15,31]])
    reduced=shape(reshape_patch(cut,{'width':50,'height':50},pixel_grid=True)['geometry'])
    assert not reduced.interiors
    restored=reshape_intent(mapping(reduced),[[16,12],[9,12],[9,28],[16,28]])
    final=shape(reshape_patch(restored,{'width':50,'height':50},pixel_grid=True)['geometry'])
    assert final.is_valid and not final.interiors
    _axis_aligned(final)


def test_cut_keeps_unedited_fractional_hole_and_does_not_leave_removed_fragments():
    from shapely.geometry import Polygon
    untouched=box(14.2,20.2,18.8,25.8);removed_hole=box(35.2,20.2,40.8,30.8)
    original=box(10,10,50,50).difference(untouched.union(removed_hole))
    intent=reshape_intent(mapping(original),[[30,5],[30,55]],True)
    result=reshape_patch(intent,{'width':100,'height':100},pixel_grid=True)
    geometry=shape(result['geometry'])
    assert geometry.geom_type=='Polygon' and len(geometry.interiors)==1
    assert Polygon(geometry.interiors[0]).equals(untouched)
    assert geometry.intersection(removed_hole).is_empty
    assert result['removed_pixels']>0


def test_fractional_retained_part_is_not_deleted_with_its_cell():
    original=box(9,10,10.4,20);candidate=box(9,10,10.2,15)
    intent={'original':mapping(original),'candidate':mapping(candidate),'window':[8,9,4,12],
            'stroke':[[8,15],[12,15]],'alternate':False}
    result=shape(reshape_patch(intent,{'width':50,'height':50},pixel_grid=True)['geometry'])
    assert result.equals(candidate)
    assert result.covers(box(10.01,10.1,10.19,14.9))


def test_existing_diagonal_does_not_invalidate_orthogonal_cut():
    from shapely.geometry import Polygon
    original=Polygon([(9,10),(10.1,10),(10.4,15),(10.4,20),(9,20)])
    candidate=original.intersection(box(0,0,10.2,15))
    intent={'original':mapping(original),'candidate':mapping(candidate),'window':[8,9,4,12],
            'stroke':[[8,15],[12,15]],'alternate':False}
    result=shape(reshape_patch(intent,{'width':50,'height':50},pixel_grid=True)['geometry'])
    assert result.symmetric_difference(candidate).area < 1e-12 and result.is_valid


def test_mixed_cell_drops_cut_sliver_but_preserves_other_components():
    from shapely.ops import unary_union
    kept=box(9,10,10.4,10.2)
    removed=box(9,10.8,10.4,11)
    connector=box(9,10,9.9,11)
    separate=box(20,10,22,12)
    original=unary_union([kept,removed,connector,separate])
    candidate=unary_union([kept,separate])
    intent={'original':mapping(original),'candidate':mapping(candidate),'window':[8,9,4,4],
            'stroke':[[8,10.2],[11,10.2]],'alternate':False}
    result=shape(reshape_patch(intent,{'width':50,'height':50},pixel_grid=True)['geometry'])
    # The central-pixel rule removes the left cell; the right cell has no
    # covered centre and must retain its candidate fraction precisely.
    assert result.is_valid and result.covers(box(10,10,10.4,10.2)) and result.covers(separate)
    assert result.intersection(removed).area < 1e-12


def test_fractional_retained_part_is_safe_when_edit_crosses_cell_diagonally():
    from shapely.geometry import Polygon
    original=box(9,10,10.4,20)
    candidate=original.intersection(Polygon([(8,9),(12,9),(10,14),(8,14)]))
    intent={'original':mapping(original),'candidate':mapping(candidate),'window':[8,9,4,12],
            'stroke':[[8,14],[12,9]],'alternate':False}
    # A subpixel legacy edge and a diagonal cannot be reconciled with exact
    # retained geometry and a pixel-edge contour; refuse instead of silently
    # deleting the retained portion or keeping a cut-away remnant.
    with pytest.raises(ValueError,match='无法安全匹配'):
        reshape_patch(intent,{'width':50,'height':50},pixel_grid=True)
