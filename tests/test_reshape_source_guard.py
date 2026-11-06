"""Raster verification is explicit and unchanged edits remain distinguishable."""
import pytest
from shapely.geometry import box,mapping,shape

from geoforma import raster,reshape


def test_single_reshape_validates_source_before_geometry(monkeypatch):
    image={'fingerprint':'expected'};calls=[]
    monkeypatch.setattr(raster,'validate_source',lambda item:(calls.append(item), 'changed'))
    monkeypatch.setattr(reshape,'reshape_geometry',lambda *args,**kwargs:pytest.fail('source changed'))
    with pytest.raises(ValueError,match='影像源已变化'):
        reshape.reshape_raster(image,mapping(box(0,0,10,10)),[[1,1],[2,2]])
    assert calls==[image]


def test_verified_geometry_does_not_reopen_source(monkeypatch):
    monkeypatch.setattr(raster,'validate_source',lambda image:pytest.fail('unexpected raster read'))
    original=mapping(box(10,10,20,20));stroke=[[12,19],[14,24],[19,22],[21,18]]
    result=reshape.reshape_geometry({'width':50,'height':50},original,stroke,pixel_grid=True)
    assert result['added_pixels']>0


def test_pixel_no_change_has_specific_exception():
    original=mapping(box(10,10,20,20));stroke=[[11,15],[9.8,15],[9.8,17],[11,17]]
    with pytest.raises(reshape.ReshapeNoChange,match='未改变任何像元'):
        reshape.reshape_geometry({'width':50,'height':50},original,stroke,pixel_grid=True)


def test_source_validation_checks_cancellation(monkeypatch):
    class Cancelled(Exception):pass
    class Task:
        def check(self):raise Cancelled()
    monkeypatch.setattr(raster,'validate_source',lambda image:pytest.fail('already cancelled'))
    with pytest.raises(Cancelled):reshape.validate_reshape_source({},Task())


@pytest.mark.parametrize('pixel_grid',[False,True])
def test_blocked_extension_is_reported_for_batch_retry(pixel_grid):
    original=box(10,10,20,20)
    intent={'original':mapping(original),'candidate':mapping(box(10,10,22,20)),
            'window':[9,9,15,12],'stroke':[[20,10],[22,10],[22,20],[20,20]],'alternate':False}
    blocked=box(21,10,22,20)
    result=reshape.reshape_patch(intent,{'width':50,'height':50},blockers=[mapping(blocked)],pixel_grid=pixel_grid)
    assert shape(result['_blocked_geometry']).equals(blocked)
    assert shape(result['geometry']).intersection(blocked).area==0


@pytest.mark.parametrize('pixel_grid',[False,True])
def test_fully_blocked_extension_preserves_retry_information(pixel_grid):
    original=box(10,10,20,20);blocked=box(20,10,22,20)
    intent={'original':mapping(original),'candidate':mapping(box(10,10,22,20)),
            'window':[9,9,15,12],'stroke':[[20,10],[22,10],[22,20],[20,20]],'alternate':False}
    with pytest.raises(reshape.ReshapeNoChange) as error:
        reshape.reshape_patch(intent,{'width':50,'height':50},blockers=[mapping(blocked)],pixel_grid=pixel_grid)
    assert shape(error.value.blocked_geometry).equals(blocked)
