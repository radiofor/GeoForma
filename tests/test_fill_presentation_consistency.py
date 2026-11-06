"""Filling changes holes, not the matched outer contour."""
from shapely.geometry import box, mapping, shape

from geoforma.label_presentation import presentation_batch


def test_fill_preserves_smoothed_exterior_and_source():
    # Smoothing a hole very close to the shell can fail topology validation;
    # filling first would incorrectly cause a different exterior to be used.
    source = mapping(box(0, 0, 20, 20).difference(box(.1, .1, 2, 2)))
    labels = [{'id': 'lake', 'status': 'confirmed', 'geometry': source}]
    options = {'enabled': True, 'value': 3}
    unfilled = shape(presentation_batch(labels, False, options)[0]['geometry'])
    filled = shape(presentation_batch(labels, True, options)[0]['geometry'])
    assert filled.exterior.equals(unfilled.exterior)
    assert len(unfilled.interiors) == 1 and not filled.interiors
    assert labels[0]['geometry'] is source and len(shape(source).interiors) == 1
