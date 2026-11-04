"""Cross-operation history and hostile project cases found in the 1.0.5 audit."""
import copy,json
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from shapely.geometry import box,mapping
from geoforma.session_validation import validate_draft
from test_reshape import workbench,raster_image


def test_class_replacement_invalidates_all_label_lookups(workbench):
    w,app,_=workbench;w.project['classes'].append({'id':2,'name':'two'});w.refresh_classes()
    old=w.current_labels()[0];w.change_label_class('target',2)
    assert old['class_id']==1 and w.current_labels()[0]['class_id']==2
    assert w.selected_label()['class_id']==2 and w.presentation_labels()[0]['class_id']==2
    w.undo_context();assert w.current_labels()[0]['class_id']==1


def test_manual_vertices_undo_redo_and_branch(workbench):
    w,app,_=workbench;w.set_tool('draw_polygon')
    w.add_manual_vertex(40,40);w.add_manual_vertex(60,40)
    w.undo_context();assert w.draft['manual_vertices']==[[40,40]]
    w.redo_context();assert w.draft['manual_vertices']==[[40,40],[60,40]]
    w.undo_context();w.add_manual_vertex(60,60)
    assert not w.prompt_redo and w.draft['manual_vertices']==[[40,40],[60,60]]
    w.undo_context();w.undo_context();w.redo_context();assert w.draft['manual_vertices']==[[40,40]]


def test_reshape_point_redo_survives_reopen(workbench):
    w,app,tmp=workbench;w.begin_reshape(auto=True)
    w.add_reshape_point(18,25);w.add_reshape_point(35,25);w.undo_context()
    w.project_path=tmp/'redo.gfm';w.save();w.cancel_reshape();w.open_project(w.project_path)
    assert w.reshape_session['stroke']==[[18,25]]
    w.redo_context();assert w.reshape_session['stroke']==[[18,25],[35,25]]
    w.undo_context();w.add_reshape_point(40,25);assert not w.reshape_session.get('redo_stroke')


def test_mixed_saved_and_draft_delete_is_one_undo(workbench):
    w,app,_=workbench;before=copy.deepcopy(w.project['labels'])
    w.draft={'geometry':mapping(box(60,60,70,70)),'pending':False,'points':[]};w.refresh_labels()
    draft=copy.deepcopy(w.draft);new=w.draft_labels()[0]['id']
    w.selected_ids={'target',new};w.delete_selected()
    assert not w.project['labels'] and not w.draft
    w.undo_context();assert w.project['labels']==before and w.draft==draft
    w.redo_context();assert not w.project['labels'] and not w.draft


def test_saved_class_edit_during_draft_can_be_undone_after_reopen(workbench):
    w,app,tmp=workbench;w.project['classes'].append({'id':2,'name':'two'});w.refresh_classes()
    w.draft={'geometry':mapping(box(60,60,70,70)),'pending':False,'points':[]};w.refresh_labels();draft=copy.deepcopy(w.draft)
    w.change_label_class('target',2)
    w.project_path=tmp/'mixed.gfm';w.save();assert w.open_project(w.project_path)
    w.undo_context();assert w.project['labels'][0]['class_id']==1 and w.draft['geometry']==json.loads(json.dumps(draft['geometry']))
    w.redo_context();assert w.project['labels'][0]['class_id']==2
    w.clear_draft();w.undo_context();assert w.project['labels'][0]['class_id']==1


def test_top_level_class_selector_is_undoable(workbench):
    w,app,_=workbench;w.project['classes'].append({'id':2,'name':'two'});w.refresh_classes()
    w.draft={'geometry':mapping(box(60,60,70,70)),'class_id':1,'points':[],'pending':False};w.refresh_labels()
    w.classes.setCurrentIndex(w.classes.findData(2));w.undo_context()
    assert w.classes.currentData()==1 and w.draft['class_id']==1
    w.redo_context();assert w.classes.currentData()==2


@pytest.mark.parametrize('damage',['collision','duplicates','unknown_class','empty_ids','batch_duplicate'])
def test_draft_identity_validation_prevents_overwriting_labels(workbench,damage):
    w,app,_=workbench;before=copy.deepcopy(w.project['labels'])
    draft={'geometry':mapping(box(60,60,70,70)),'points':[],'pending':False}
    if damage=='collision':draft['display_ids']=['target']
    elif damage=='duplicates':draft['display_ids']=['new','new']
    elif damage=='unknown_class':draft.update(display_ids=['new'],part_classes={'new':99})
    elif damage=='empty_ids':draft['display_ids']=[]
    else:
        one=dict(draft,base_id='target',display_ids=['target'])
        draft=dict(one,reshape_batch=[copy.deepcopy(one),copy.deepcopy(one)])
    w.draft=draft
    if damage=='empty_ids':
        w.confirm();assert len(w.project['labels'])==2
    else:
        with pytest.raises(ValueError):validate_draft(draft,w.image['id'],{w.image['id']},{l['id']:l for l in before},{1})
        w.confirm();assert w.project['labels']==before


def test_delete_in_text_input_does_not_delete_labels(workbench):
    w,app,_=workbench;w.show();app.processEvents();before=copy.deepcopy(w.project['labels'])
    field=w.export_label_field_input;field.setText('abcd');field.setCursorPosition(1);field.setFocus()
    QTest.keyClick(field,Qt.Key.Key_Delete);assert field.text()=='acd' and w.project['labels']==before


@pytest.mark.parametrize('auto',[False,True])
def test_cancel_after_result_before_finished_does_not_stage_a_reshape(workbench,monkeypatch,auto):
    from threading import Event
    from types import SimpleNamespace
    from test_reshape import OUT
    from geoforma.reshape import reshape_raster
    w,app,_=workbench;before=copy.deepcopy(w.project['labels'])
    result=reshape_raster(w.image,before[0]['geometry'],OUT)
    w.begin_reshape(auto=auto);w.reshape_session['stroke']=copy.deepcopy(OUT)
    def run(title,work,done,**options):
        token=SimpleNamespace(cancel_event=Event());w.task=token;w.task_kind='reshape'
        done([result] if auto else result);token.cancel_event.set();w.task=None;w.task_kind=None
        options['on_finished']()
    monkeypatch.setattr(w,'run',run);w.finish_reshape()
    assert not w.draft and w.project['labels']==before


@pytest.mark.parametrize('mode',['foreign_image','wrong_id','negative_index','duplicate','no_snapshot'])
def test_invalid_composite_history_is_rejected(workbench,mode):
    from geoforma.session_validation import validate_sessions
    w,app,_=workbench;old=copy.deepcopy(w.project['labels'][0]);entries=[['target',old,0]]
    if mode=='foreign_image':old['image_id']='foreign'
    elif mode=='wrong_id':old['id']='different'
    elif mode=='negative_index':entries[0][2]=-1
    elif mode=='duplicate':entries*=2
    record={'_label_entries':entries,'_draft':{}}
    if mode=='no_snapshot':record.pop('_draft')
    w.image['mode_sessions']={'individual':{'draft':{},'undo':[record]}}
    with pytest.raises(ValueError):validate_sessions(w.project)


def test_label_undo_shortcut_routes_the_latest_composite_operation(workbench):
    w,app,_=workbench;before=copy.deepcopy(w.project['labels'])
    w.draft={'geometry':mapping(box(60,60,70,70)),'points':[],'pending':False};w.refresh_labels()
    w.select_label('target');w.delete_selected();assert not w.project['labels']
    assert w.undo_label_action.isEnabled();w.undo_label_action.trigger()
    assert w.project['labels']==before and w.draft.get('geometry')


def test_class_management_keeps_references_from_composite_and_part_history():
    from geoforma.editing_state import referenced_draft_classes
    record={'draft':{'class_id':2,'part_classes':{'new':3}},'undo':[{'_draft':{'class_id':4},'_label_entries':[['old',{'class_id':5},0]]}]}
    assert referenced_draft_classes(record)=={2,3,4,5}
