"""A class-only draft must not divert saved reshape history."""
import copy,time
from shapely.geometry import shape
from test_reshape import workbench,raster_image,OUT


def test_class_only_state_keeps_reshape_undo_after_save_and_reopen(workbench):
    w,app,tmp=workbench;w.smooth_enabled.setChecked(False)
    original=copy.deepcopy(w.project['labels'][0]);w.draft={'class_id':1}
    w.begin_reshape(auto=True)
    for x,y in OUT:w.add_reshape_point(x,y)
    w.finish_reshape();deadline=time.monotonic()+8
    while w.task and time.monotonic()<deadline:app.processEvents();time.sleep(.002)
    assert w.task is None and w.reshape_session is None
    changed=copy.deepcopy(w.project['labels'][0]);assert not shape(changed['geometry']).equals(shape(original['geometry']))
    assert len(w.label_undo)==1 and not w.prompt_undo
    path=tmp/'history.gfm';w.project_path=path;w.save();assert w.open_project(path)
    w.undo_context();assert shape(w.project['labels'][0]['geometry']).equals(shape(original['geometry']))
    w.redo_context();assert shape(w.project['labels'][0]['geometry']).equals(shape(changed['geometry']))
