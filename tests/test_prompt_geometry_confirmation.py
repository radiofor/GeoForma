"""After generation, confirmation uses geometry rather than old prompts."""
import pytest
from shapely.geometry import MultiPolygon,box,mapping,shape
from test_reshape import workbench,raster_image


@pytest.mark.parametrize('prompt',[
    {'points':[[62,62,1]],'box':None},
    {'points':[],'box':[60,60,64,64]},
])
def test_confirm_uses_generated_geometry_not_old_point_or_box(workbench,prompt):
    from geoforma.storage import save_project,load_project
    w,app,tmp=workbench;w.project['labels']=[];w.single_polygon.setChecked(True)
    large=box(20,20,30,30);small=box(60,60,64,64)
    w.draft={'geometry':mapping(MultiPolygon([large,small])),'pending':False,**prompt}
    w.refresh_labels();w.confirm()
    assert len(w.project['labels'])==1 and shape(w.project['labels'][0]['geometry']).equals(large)
    w.capture_workspace();path=tmp/'confirmed.gfm';save_project(w.project,path)
    assert shape(load_project(path)['labels'][0]['geometry']).equals(large)
    w.undo_label();assert not w.project['labels']
    w.redo_label();assert shape(w.project['labels'][0]['geometry']).equals(large)


@pytest.mark.parametrize('prompt',[
    {'points':[[21,25,1]],'box':None},
    {'points':[],'box':[20,20,23,30]},
])
def test_conflict_resolution_is_identical_for_old_point_and_box(workbench,prompt):
    w,app,_=workbench;w.single_polygon.setChecked(True)
    blocker=dict(w.project['labels'][0],id='blocker',geometry=mapping(box(24,20,25,30)))
    w.project['labels']=[blocker]
    w.draft={'geometry':mapping(box(20,20,30,30)),'pending':False,**prompt}
    w.refresh_labels();w.confirm()
    saved=next(label for label in w.project['labels'] if label['id']!='blocker')
    assert shape(saved['geometry']).equals(box(25,20,30,30))
    w.undo_label();assert w.project['labels']==[blocker]
