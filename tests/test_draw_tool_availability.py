"""Manual draw availability tracks the unfinished annotation state."""
import copy
import pytest
from shapely.geometry import box,mapping
from test_reshape import workbench,raster_image


@pytest.mark.parametrize('draft',[
    {'geometry':mapping(box(40,40,50,50))}, {'points':[[5,5,1]]},
    {'box':[1,1,5,5]}, {'pending':True}, {'base_id':'target'},
])
def test_unfinished_annotation_disables_draw_action_and_button(workbench,draft):
    w,app,_=workbench;w.draft=copy.deepcopy(draft);w.update_controls()
    action=w.mode_actions['draw_polygon'];button=w.image_toolbar.widgetForAction(action)
    assert not action.isEnabled() and not button.isEnabled()
    before=copy.deepcopy(w.draft);w.set_tool('draw_polygon');w.add_manual_vertex(60,60)
    assert w.draft==before and w.view.selected_mode!='draw_polygon'
    w.clear_draft();assert action.isEnabled() and button.isEnabled()


def test_drawing_can_continue_but_new_draw_waits_for_save(workbench):
    w,app,_=workbench;w.set_tool('draw_polygon')
    for x,y in ((40,40),(60,40),(60,60)):
        w.add_manual_vertex(x,y)
        assert w.mode_actions['draw_polygon'].isEnabled()
    w.undo_manual_vertex();assert len(w.draft['manual_vertices'])==2
    w.add_manual_vertex(60,60);w.finish_manual_polygon()
    assert w.draft.get('geometry') and not w.mode_actions['draw_polygon'].isEnabled()
    before=copy.deepcopy(w.draft);w.add_manual_vertex(70,70);assert w.draft==before
    w.confirm();assert not w.draft and w.mode_actions['draw_polygon'].isEnabled()


def test_class_only_state_does_not_block_a_new_drawing(workbench):
    w,app,_=workbench;w.draft={'class_id':1};w.update_controls()
    assert w.mode_actions['draw_polygon'].isEnabled()
    w.set_tool('draw_polygon');w.add_manual_vertex(40,40)
    assert w.draft['manual_vertices']==[[40,40]]


def test_draw_entry_respects_reshape_and_project_transition(workbench):
    w,app,_=workbench;w.begin_reshape(auto=True)
    w.add_manual_vertex(40,40);assert not w.draft
    w.cancel_reshape();w.project_transition=object()
    try:
        w.add_manual_vertex(40,40);assert not w.draft
    finally:w.project_transition=None
