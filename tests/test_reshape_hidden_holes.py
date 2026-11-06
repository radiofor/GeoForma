import pytest
from shapely.geometry import box, mapping, shape

from geoforma.reshape import reshape_geometry, reshape_reference_intent
from geoforma.smoothing import smooth_geometry


def test_smoothed_external_edit_preserves_hidden_holes_when_display_holes_differ():
    raw = box(10, 10, 20, 20).difference(box(13, 13, 15, 15))
    # The displayed outer ring can be clipped or simplified independently of
    # hidden interiors.  It is still a valid reference for an outer edit.
    shown = box(8, 10, 20, 20)
    stroke = [[9, 9], [9, 21]]
    result = reshape_geometry(
        {'width': 100, 'height': 100}, mapping(raw), stroke,
        reference=mapping(shown), include_holes=False, pixel_grid=True,
    )
    geometry = shape(result['geometry'])
    assert geometry.is_valid
    assert len(geometry.interiors) == 1
    assert geometry.interiors[0].equals(raw.interiors[0])
    assert geometry.bounds == (9, 10, 20, 20)


def test_visible_hole_edits_still_require_matching_rings():
    raw = box(10, 10, 20, 20).difference(box(13, 13, 15, 15))
    with pytest.raises(ValueError, match='不匹配'):
        reshape_reference_intent(
            mapping(raw), mapping(box(8, 10, 20, 20)), [[12, 14], [16, 14]],
            include_holes=True,
        )


@pytest.mark.parametrize('reference', ['none', 'raw', 'smooth'])
@pytest.mark.parametrize('include_holes', [False, True])
@pytest.mark.parametrize('reverse', [False, True])
@pytest.mark.parametrize('alternate', [False, True])
def test_outer_cut_across_holes_preserves_retained_parts(reference, include_holes, reverse, alternate):
    raw = box(10, 10, 70, 60).difference(box(20, 20, 30, 40).union(box(40, 20, 50, 40)))
    stroke = [[25, 5], [25, 65]]
    if reverse:
        stroke.reverse()
    result = reshape_geometry(
        {'width': 100, 'height': 100}, mapping(raw), stroke,
        reference=(smooth_geometry(mapping(raw), 1) if reference == 'smooth' else mapping(raw) if reference == 'raw' else None), include_holes=include_holes,
        alternate=alternate, pixel_grid=True,
    )
    output = shape(result['geometry'])
    retained = box(10, 10, 25, 60) if output.bounds[0] == 10 else box(25, 10, 70, 60)
    assert output.is_valid
    assert output.equals(raw.intersection(retained))


@pytest.mark.parametrize('reference', [False, True])
def test_line_crossing_only_holes_edits_holes(reference):
    raw = box(10, 10, 70, 50).difference(box(20, 20, 30, 40).union(box(45, 20, 55, 40)))
    result = reshape_geometry(
        {'width': 100, 'height': 100}, mapping(raw), [[15, 30], [60, 30]],
        reference=mapping(raw) if reference else None, include_holes=True, pixel_grid=True,
    )
    output = shape(result['geometry'])
    assert output.is_valid
    assert not output.intersection(box(20, 20, 30, 40)).equals(raw.intersection(box(20, 20, 30, 40)))
    assert not output.intersection(box(45, 20, 55, 40)).equals(raw.intersection(box(45, 20, 55, 40)))


@pytest.mark.parametrize('reference', [False, True])
def test_line_crossing_only_hidden_holes_does_not_edit(reference):
    raw = box(10, 10, 70, 50).difference(box(20, 20, 30, 40).union(box(45, 20, 55, 40)))
    with pytest.raises(ValueError, match='穿过'):
        reshape_geometry(
            {'width': 100, 'height': 100}, mapping(raw), [[15, 30], [60, 30]],
            reference=mapping(raw) if reference else None, include_holes=False, pixel_grid=True,
        )
