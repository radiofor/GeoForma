"""Manual edits and smoothing must use the latest contour, never an old seed."""
import threading
import time

import pytest
from shapely.geometry import box,mapping,shape
from test_reshape import workbench,raster_image


def test_reshape_builds_detached_record_without_copying_old_geometry():
    from geoforma.editing_state import reshaped_label
    class OldGeometry(dict):
        def __deepcopy__(self,memo):raise AssertionError('旧几何不应在构造新记录时复制')
    original={'id':'target','geometry':OldGeometry(mapping(box(0,0,5,5))),
              'model':{'backend':'sam','variant':'x'},'points':[[1,2,1]],
              'manual_edits':[{'tool':'draw_polygon'}],'source_geometry':{'obsolete':True},'edge':True}
    new=mapping(box(0,0,8,5));stroke=[[5,1],[8,1]]
    result={'geometry':new,'stroke':stroke,'alternate':False,'window':[0,0,8,5],'added_pixels':15,'removed_pixels':0}
    updated=reshaped_label(original,result)
    assert updated['geometry'] is new and updated['editing_state']=='manual' and not updated['edge']
    assert updated['model']==original['model'] and updated['points']==original['points']
    assert updated['model'] is not original['model'] and updated['points'] is not original['points']
    assert len(original['manual_edits'])==1 and len(updated['manual_edits'])==2
    assert updated['manual_edits'][-1]['stroke']==stroke and updated['manual_edits'][-1]['stroke'] is not stroke
    assert 'source_geometry' not in updated


def test_manual_draft_drops_old_seed_and_reopen_does_not_restore_it(workbench):
    from geoforma.project_loading import prepare_project
    from geoforma.storage import save_project
    w,app,tmp=workbench
    before=w.project['labels'][0]['geometry'];after=mapping(box(20,20,35,30))
    edited={'base_id':'target','geometry':after,'seed_geometry':before,'class_id':1,'editing_state':'manual'}
    w.project['workspace']={'image_id':w.image['id'],'draft':edited}
    path=tmp/'manual.gfm';save_project(w.project,path)
    restored=prepare_project(path,(800,600),read_frame=False)
    assert shape(restored.draft['geometry']).equals(shape(after)) and 'seed_geometry' not in restored.draft


def test_smoothing_sources_follow_consecutive_edits_while_index_is_rebuilding(workbench,monkeypatch):
    from geoforma.controllers import label_list
    w,app,_=workbench;template=w.project['labels'][0]
    for i in range(33):
        x=40+(i%9)*6;y=40+(i//9)*6
        w.project['labels'].append(dict(template,id=f'extra-{i}',geometry=mapping(box(x,y,x+3,y+3))))
    w.refresh_labels()
    deadline=time.monotonic()+8
    while w.label_index_task is not None:
        app.processEvents();time.sleep(.002);assert time.monotonic()<deadline
    original=label_list.LabelIndex;started=threading.Event();release=threading.Event()
    def blocked(labels,task=None):
        started.set()
        while not release.wait(.005):
            if task:task.check()
        return original(labels,task=task)
    monkeypatch.setattr(label_list,'LabelIndex',blocked)
    try:
        for right in (32,35):
            geometry=mapping(box(20,20,right,30))
            w.project['labels']=[dict(label,geometry=geometry,editing_state='manual') if label['id']=='target' else label for label in w.project['labels']]
            w.refresh_labels()
            while not started.is_set():app.processEvents();time.sleep(.002);assert time.monotonic()<deadline
            sources=w.smoothing_sources(None)
            assert next(label for label in sources if label['id']=='target')['geometry'] is geometry
    finally:
        release.set()
        while w.label_index_task is not None:
            app.processEvents();time.sleep(.002);assert time.monotonic()<deadline


@pytest.mark.parametrize('smooth',[False,True])
def test_cut_away_old_hole_then_redraw_save_and_undo(workbench,smooth):
    from geoforma.storage import save_project,load_project
    from test_smoothing import settled
    w,app,tmp=workbench;w.single_polygon.setChecked(False);w.smooth_enabled.setChecked(smooth)
    hole=box(35.2,20.2,40.8,30.8)
    initial=box(10,10,50,50).difference(hole)
    w.project['labels'][0]['geometry']=mapping(initial);w.refresh_labels()
    def reshape(stroke,alternate=False):
        w.begin_reshape(auto=True)
        for x,y in stroke:w.add_reshape_point(x,y)
        if alternate:w.reshape_alternate()
        w.finish_reshape();deadline=time.monotonic()+8
        while w.task and time.monotonic()<deadline:app.processEvents();time.sleep(.002)
        assert w.task is None and w.reshape_session is None
        if smooth:settled(w,app)
    reshape([[30,5],[30,55]],True)
    assert len(w.project['labels'])==1
    first=shape(w.project['labels'][0]['geometry']);assert first.equals(box(10,10,30,50))
    reshape([[29,12],[45,12],[45,48],[29,48]])
    assert len(w.project['labels'])==1
    final=shape(w.project['labels'][0]['geometry']);assert final.is_valid and final.intersection(hole).equals(hole)
    w.undo_label();assert shape(w.project['labels'][0]['geometry']).equals(first)
    w.undo_label();assert shape(w.project['labels'][0]['geometry']).equals(initial)
    w.redo_label();w.redo_label();assert shape(w.project['labels'][0]['geometry']).equals(final)
    w.capture_workspace();path=tmp/'redrawn.gfm';save_project(w.project,path)
    restored=shape(load_project(path)['labels'][0]['geometry'])
    assert restored.is_valid and restored.equals(final) and restored.intersection(hole).equals(hole)
