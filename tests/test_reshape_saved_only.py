"""Only saved annotations can enter or be changed by reshape."""
import copy,time
import pytest
from shapely.geometry import box,mapping
from geoforma.tool_state import has_unsaved_annotation
from test_reshape import workbench,raster_image,OUT


@pytest.mark.parametrize('draft',[
    {'geometry':mapping(box(40,20,50,30))},
    {'base_id':'target','geometry':mapping(box(20,20,30,30))},
    {'points':[[5,5,1]]}, {'box':[1,1,5,5]},
    {'manual_vertices':[[1,1],[5,1]]}, {'pending':True},
    {'reshape_batch':[{'geometry':mapping(box(5,5,10,10))}]},
])
def test_unsaved_draft_blocks_all_reshape_entry_points(workbench,draft):
    w,app,_=workbench;w.draft=copy.deepcopy(draft);w.update_controls()
    before=copy.deepcopy(w.project['labels']);previous=copy.deepcopy(w.draft)
    assert has_unsaved_annotation(w.draft) and not w.mode_actions['reshape'].isEnabled()
    w.begin_reshape(auto=True);w.begin_reshape();w.set_tool('reshape')
    assert w.reshape_session is None and w.draft==previous and w.project['labels']==before
    assert w.view.selected_mode!='reshape'


def test_saved_selection_and_class_only_state_do_not_block_reshape(workbench):
    w,app,_=workbench;w.draft={'class_id':1};w.update_controls()
    assert not has_unsaved_annotation(w.draft) and w.mode_actions['reshape'].isEnabled()
    w.begin_reshape(auto=True)
    assert w.reshape_session and w.reshape_session['target']=='auto'


def test_save_draft_then_reshape_without_selection(workbench):
    w,app,_=workbench;w.project['labels']=[];w.selected_ids.clear();w.selected_id=None
    w.draft={'geometry':mapping(box(20,20,30,30)),'points':[],'pending':False};w.refresh_labels()
    assert not w.mode_actions['reshape'].isEnabled()
    w.confirm();assert not w.draft and len(w.project['labels'])==1
    w.selected_ids.clear();w.selected_id=None;w.refresh_labels()
    assert w.mode_actions['reshape'].isEnabled();w.begin_reshape(auto=True)
    for x,y in OUT:w.add_reshape_point(x,y)
    w.finish_reshape();deadline=time.monotonic()+8
    while w.task and time.monotonic()<deadline:app.processEvents();time.sleep(.002)
    assert w.task is None and w.reshape_session is None and w.project['labels'][0]['editing_state']=='manual'


def test_pending_draft_cannot_be_edited_by_stale_reshape_result(workbench):
    w,app,_=workbench;w.begin_reshape(auto=True);session=w.reshape_session
    before=copy.deepcopy(w.project['labels']);w.draft={'points':[[2,2,1]]}
    result={'geometry':mapping(box(20,20,30,34)),'stroke':OUT,'alternate':False,'window':[20,20,10,14],
            'added_pixels':24,'removed_pixels':0}
    w.apply_reshape_results(session,[('label',before[0])],[result])
    assert w.project['labels']==before and w.draft=={'points':[[2,2,1]]}


def test_restored_tool_does_not_reactivate_reshape_with_draft(workbench):
    w,app,_=workbench;w.draft={'geometry':mapping(box(20,20,30,30))}
    w.restore_tool('reshape')
    assert w.view.selected_mode=='pan' and not w.view.reshape_enabled


def test_reshape_is_unavailable_without_saved_labels(workbench):
    w,app,_=workbench;w.project['labels']=[];w.selected_ids.clear();w.selected_id=None
    w.refresh_labels();w.update_controls()
    assert not w.mode_actions['reshape'].isEnabled()
    w.begin_reshape(auto=True);assert w.reshape_session is None
    w.restore_tool('reshape');assert w.view.selected_mode=='pan'
