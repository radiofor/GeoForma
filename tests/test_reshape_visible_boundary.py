"""Target selection follows the visible contour without losing hidden holes."""
from types import SimpleNamespace
import pytest

from shapely.geometry import LineString,MultiPolygon,Polygon,box, mapping, shape
from test_reshape import workbench, raster_image


def test_reference_reshape_preserves_unedited_jagged_arcs():
    from geoforma.reshape import reshape_reference_intent
    raw=Polygon([(20,20),(22,20),(22,19),(24,19),(24,20),(30,20),(30,30),(20,30)])
    visible=box(20,19,32,32)
    result=shape(reshape_reference_intent(mapping(raw),mapping(visible),[[19,31],[33,31]])['candidate'])
    untouched=LineString([(20,20),(22,20),(22,19),(24,19),(24,20),(30,20)])
    assert result.is_valid and result.boundary.covers(untouched)
    assert result.area>raw.area


def test_reference_components_match_spatially_after_reordering():
    from geoforma.reshape import reshape_reference_intent
    left=box(0,0,10,10);right=box(20,0,30,10)
    raw=MultiPolygon([left,right]);visible=MultiPolygon([box(20,0,32,12),left])
    result=shape(reshape_reference_intent(mapping(raw),mapping(visible),[[19,11],[33,11]])['candidate'])
    assert result.is_valid and result.covers(left)
    assert result.intersection(box(0,0,10,10)).equals(left)
    assert result.area>raw.area


def test_reference_holes_match_spatially_after_reordering():
    from geoforma.reshape import reshape_reference_intent
    left=box(5,5,10,10);right=box(30,10,35,15)
    raw=Polygon(box(0,0,50,40).exterior.coords,[left.exterior.coords,right.exterior.coords])
    visible=Polygon(box(0,0,50,40).exterior.coords,[box(29,9,36,16).exterior.coords,left.exterior.coords])
    result=shape(reshape_reference_intent(mapping(raw),mapping(visible),[[28,9.5],[37,9.5]])['candidate'])
    assert result.is_valid and len(result.interiors)==2
    assert any(Polygon(ring).equals(left) for ring in result.interiors)
    assert not result.equals(raw)


def test_ambiguous_reference_ring_match_is_rejected():
    from geoforma.reshape import _match_polygons
    with pytest.raises(ValueError):
        _match_polygons([box(0,0,4,4),box(6,0,10,4)],[box(2,0,8,4),box(20,0,24,4)])


def test_smooth_fallback_keeps_hidden_holes_and_ignores_single_crossing(workbench, monkeypatch):
    from geoforma import reshape, smoothing
    w,app,_=workbench
    hole=box(24,24,25,25)
    raw=box(20,20,30,30).difference(hole)
    visible=box(20,20,32,32).difference(hole)
    target=w.project['labels'][0];target['geometry']=mapping(raw)
    w.project['labels'].append(dict(target,id='other',geometry=mapping(box(40,20,50,32))))
    w.smooth_enabled.setChecked(True);w.fill_holes.setChecked(True)
    monkeypatch.setattr(w,'visible_reshape_geometries',lambda records:{r['id']:mapping(visible) if r['id']=='target' else r['geometry'] for r in records})
    monkeypatch.setattr(smoothing,'smooth_batch',lambda records,*args,**kwargs:[dict(r,geometry=mapping(visible)) if r['id']=='target' else r for r in records])
    captured=[];work=[]
    def fake(image,geometry,stroke,blockers,bounds,single,alternate,task,include_holes=True,reference=None,pixel_grid=False):
        captured.append((shape(geometry),include_holes,shape(reference),pixel_grid))
        return {'geometry':geometry}
    monkeypatch.setattr(reshape,'reshape_geometry',fake)
    monkeypatch.setattr(w,'run',lambda title,fn,*args,**kwargs:work.append(fn))
    w.begin_reshape(auto=True)
    for point in [[19,31],[45,31]]:w.add_reshape_point(*point)
    w.finish_reshape()
    targets,_=work[0](SimpleNamespace(check=lambda:None))
    assert [label['id'] for _,label in targets]==['target']
    assert captured[0][0].equals(raw) and captured[0][2].equals(visible)
    assert len(captured[0][0].interiors)==1
    assert captured[0][1] is False and captured[0][3] is True


def test_raw_geometry_preferred_when_both_outlines_cross(workbench,monkeypatch):
    from geoforma import reshape, smoothing
    w,app,_=workbench;raw=w.project['labels'][0]['geometry'];w.smooth_enabled.setChecked(True)
    work=[];captured=[]
    monkeypatch.setattr(smoothing,'smooth_batch',lambda records,*args,**kwargs:records)
    monkeypatch.setattr(reshape,'reshape_geometry',lambda image,geometry,*args,**kwargs:captured.append(geometry) or {'geometry':geometry})
    monkeypatch.setattr(w,'run',lambda title,fn,*args,**kwargs:work.append(fn))
    w.begin_reshape(auto=True)
    for point in [[19,25],[31,25]]:w.add_reshape_point(*point)
    w.finish_reshape();work[0](SimpleNamespace(check=lambda:None))
    assert captured[0] is raw


def test_fallback_commit_and_undo_preserve_hidden_hole(workbench,monkeypatch):
    from geoforma import reshape, smoothing
    w,app,_=workbench;hole=box(24,24,25,25)
    raw=box(20,20,30,30).difference(hole)
    visible=box(20,20,32,32).difference(hole)
    w.project['labels'][0]['geometry']=mapping(raw)
    w.smooth_enabled.setChecked(True);w.fill_holes.setChecked(True)
    monkeypatch.setattr(w,'visible_reshape_geometries',lambda records:{r['id']:mapping(visible) for r in records})
    monkeypatch.setattr(smoothing,'smooth_batch',lambda records,*args,**kwargs:[dict(r,geometry=mapping(visible)) for r in records])
    monkeypatch.setattr(reshape,'reshape_geometry',lambda image,geometry,stroke,blockers,bounds,single,alternate,task,include_holes=True,reference=None,pixel_grid=False:
                        reshape.reshape_patch(reshape.reshape_reference_intent(geometry,reference,stroke,alternate,include_holes) if reference is not None else reshape.reshape_intent(geometry,stroke,alternate,include_holes),image,blockers=blockers,pixel_grid=pixel_grid))
    work=[];monkeypatch.setattr(w,'run',lambda title,fn,*args,**kwargs:work.append(fn))
    w.begin_reshape(auto=True)
    for point in [[19,31],[33,31]]:w.add_reshape_point(*point)
    w.finish_reshape();targets,results=work[0](SimpleNamespace(check=lambda:None))
    w.apply_reshape_results(w.reshape_session,targets,results)
    after=shape(w.project['labels'][0]['geometry'])
    assert after.is_valid and len(after.interiors)==1 and after.intersection(hole).area==0
    assert after.boundary.covers(box(20,20,30,30).boundary.intersection(box(19,19,31,29)))
    w.undo_label();assert shape(w.project['labels'][0]['geometry']).equals(raw)
