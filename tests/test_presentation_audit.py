"""Presentation isolation and recovery after a background failure."""
from shapely.geometry import box, mapping, shape

from geoforma.smoothing import smooth_batch
from test_reshape import workbench, raster_image


def test_smoothing_does_not_partition_labels_from_different_images():
    source=mapping(box(10,10,20,20))
    labels=[{'id':'a','image_id':'one','status':'confirmed','geometry':source},
            {'id':'b','image_id':'two','status':'confirmed','geometry':source}]
    result=smooth_batch(labels,1)
    assert len(result)==2 and shape(result[0]['geometry']).equals(shape(result[1]['geometry']))


def test_smoothing_failure_reenables_reshape_after_hold(workbench,monkeypatch):
    w,app,_=workbench
    w._reshape_smoothing_hold=('waiting',)
    w.update_controls()
    assert not w.mode_actions['reshape'].isEnabled()
    monkeypatch.setattr(w,'redraw',lambda:None)
    w.smoothing_error('failure')
    assert w._reshape_smoothing_hold is None
    assert w.mode_actions['reshape'].isEnabled()
