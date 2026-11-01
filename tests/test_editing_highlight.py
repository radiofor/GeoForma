"""Editing is distinct from selection and only restyles retained geometry."""
from shapely.geometry import box, mapping
from geoforma.theme import EDITING, SELECTION
from geoforma.rendering.label_item import LABEL_RED
from test_reshape import workbench, raster_image


def test_normal_selected_and_editing_have_distinct_retained_styles(workbench):
    w,app,_=workbench
    labels=[dict(id=str(i),status='confirmed',geometry=mapping(box(10+i*20,10,20+i*20,20))) for i in range(3)]
    w.view.overlays(labels,selected={'1'},editing_id='2')
    items=dict(w.view.overlay_records)
    assert [items[str(i)].pen().color().name() for i in range(3)]==[LABEL_RED,SELECTION,EDITING]
    assert items['2'].brush().color().alpha()==0
    paths={key:item.path() for key,item in items.items()}
    w.view.overlays(labels,selected={'2'})
    for key,item in items.items():
        assert w.view.overlay_records[key] is item and item.path()==paths[key]
    assert items['2'].pen().color().name()==SELECTION
    assert items['1'].pen().color().name()==LABEL_RED


def test_draft_keeps_editing_highlight_while_pending_or_deselected(workbench):
    w,app,_=workbench;geometry=mapping(box(20,20,30,30))
    w.view.overlays([],geometry)
    item=w.view.overlay_records['__draft'];state=item.render_state
    w.view.overlays([],geometry,pending=True,draft_id='target')
    assert w.view.overlay_records['__draft'] is item and item.render_state==state
    assert item.pen().color().name()==EDITING
    assert item.brush().color().alpha()==0


def test_reshape_highlight_returns_to_selection_on_cancel(workbench):
    w,app,_=workbench
    item=w.view.overlay_records['target']
    assert item.pen().color().name()==SELECTION
    w.begin_reshape()
    assert w.view.overlay_records['target'] is item
    assert item.pen().color().name()==EDITING
    assert item.brush().color().alpha()==0
    w.cancel_reshape()
    assert w.view.overlay_records['target'] is item
    assert item.pen().color().name()==LABEL_RED
