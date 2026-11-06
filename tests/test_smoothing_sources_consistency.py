"""Restored and live workspaces use the same authoritative smoothing inputs."""
from shapely.geometry import box,mapping,shape
from test_reshape import workbench,raster_image


def test_project_load_and_live_smoothing_use_same_draft_sources(workbench):
    from geoforma.project_loading import prepare_project
    from geoforma.storage import save_project
    w,app,tmp=workbench
    w.draft={'geometry':mapping(box(40,40,50,50)),'points':[],'pending':False,'class_id':1}
    w.smooth_enabled.setChecked(True);w.refresh_labels()
    live=w.smoothing_sources(w.draft['geometry'])
    w.capture_workspace();path=tmp/'draft.gfm';save_project(w.project,path)
    loaded=prepare_project(path,(800,600),read_frame=False)
    restored=loaded.smoothing[0]
    assert [(r['id'],r['status']) for r in restored]==[(r['id'],r['status']) for r in live]
    assert all(shape(a['geometry']).equals(shape(b['geometry'])) for a,b in zip(restored,live))
    assert restored[-1].keys()=={'id','geometry','status'}
