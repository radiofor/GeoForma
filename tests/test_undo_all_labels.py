"""Whole-history button rollback, independent shortcut steps and redo order."""
import copy
from shapely.geometry import box,mapping,shape
from test_workbench import workbench,fake_image


def ready_image(w):
    image=fake_image('image');image['ready']=True;w.project['images']=[image]
    w.refresh_images();w.images.setCurrentRow(0);return image


def save_label(w,x):
    w.draft={'geometry':mapping(box(x,100,x+40,140)),'points':[],'pending':False}
    w.confirm();return w.selected_id


def test_enter_saves_on_canvas_but_does_not_interrupt_text_editing(workbench):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    w,app,wait,errors=workbench;ready_image(w)
    w.draft={'geometry':mapping(box(100,100,140,140)),'points':[],'pending':False};w.update_controls()
    w.view.setFocus();app.processEvents();QTest.keyClick(w.view,Qt.Key.Key_Return);wait()
    assert len(w.project['labels'])==1 and not w.draft
    w.draft={'geometry':mapping(box(300,100,340,140)),'points':[],'pending':False};w.update_controls()
    w.export_label_field_input.setFocus();app.processEvents();QTest.keyClick(w.export_label_field_input,Qt.Key.Key_Return);app.processEvents()
    assert len(w.project['labels'])==1 and w.draft.get('geometry')
    w.view.setFocus();app.processEvents();QTest.keyClick(w.view,Qt.Key.Key_Enter);wait()
    assert len(w.project['labels'])==2 and not errors


def test_button_undoes_the_entire_history_and_keeps_stepwise_redo(workbench):
    w,app,wait,errors=workbench;ready_image(w)
    baseline=dict(id='baseline',image_id='image',annotation_mode='individual',status='confirmed',class_id=1,geometry=mapping(box(10,10,30,30)))
    w.project['labels']=[baseline];first=save_label(w,100);second=save_label(w,300)
    w.select_label(first);w.delete_selected();w.select_label(second);w.edit_selected(locate=False)
    w.draft['geometry']=mapping(box(310,100,360,150));w.confirm();wait()
    final=copy.deepcopy(w.project['labels']);assert len(w.label_undo)==4
    assert not hasattr(w,'undo_label_button') and w.undo_all_label_action.shortcut().isEmpty()
    w.undo_all_labels();wait()
    assert w.project['labels']==[baseline] and not w.label_undo and len(w.label_redo)==4
    assert not w.undo_all_label_action.isEnabled() and w.redo_prompt_action.isEnabled()
    w.redo_prompt_action.trigger();wait()
    assert {label['id'] for label in w.project['labels']}=={'baseline',first} and len(w.label_redo)==3
    for _ in range(3):w.redo_prompt_action.trigger();wait()
    assert w.project['labels']==final and not w.label_redo and not errors


def test_shortcut_actions_keep_undoing_one_operation(workbench):
    w,app,wait,errors=workbench;ready_image(w);first=save_label(w,100);save_label(w,300)
    assert w.undo_label_action.shortcut().toString()=='Ctrl+Alt+Z'
    assert w.undo_prompt_action.shortcut().toString()=='Ctrl+Z'
    w.undo_label_action.trigger();wait()
    assert [label['id'] for label in w.project['labels']]==[first] and len(w.label_undo)==1
    w.undo_prompt_action.trigger();wait();assert not w.project['labels'] and not w.label_undo
    assert len(w.label_redo)==2 and not errors


def test_all_undo_preflights_an_older_modified_target_without_partial_rollback(workbench):
    w,app,wait,errors=workbench;ready_image(w);first=save_label(w,100);save_label(w,300)
    w.select_label(first);w.edit_selected(locate=False);w.add_point(120,120,1)
    labels=copy.deepcopy(w.project['labels']);draft=copy.deepcopy(w.draft)
    w.undo_all_labels();wait()
    assert w.project['labels']==labels and w.draft==draft and len(w.label_undo)==2 and not w.label_redo
    assert w.statusBar().currentMessage()
    w.clear_draft();w.undo_all_labels();wait();assert not w.project['labels'] and not errors


def test_whole_history_rollback_includes_legacy_candidate_edits(workbench):
    w,app,wait,errors=workbench;ready_image(w);individual=save_label(w,100)
    candidate=dict(id='candidate',image_id='image',annotation_mode='automatic',status='candidate',class_id=None,
                   geometry=mapping(box(300,300,380,380)),window=[0,0,1024,1024])
    w.project['labels'].append(candidate);w.refresh_labels();wait()
    w.select_label('candidate');w.confirm();wait()
    assert next(label for label in w.project['labels'] if label['id']=='candidate')['status']=='confirmed'
    w.undo_all_labels();wait()
    assert not any(label['id']==individual for label in w.project['labels'])
    assert w.project['labels']==[candidate] and not w.label_undo and not errors


def test_whole_history_action_is_locked_during_task_and_polygon_edit(workbench):
    w,app,wait,errors=workbench;ready_image(w);identifier=save_label(w,100);before=copy.deepcopy(w.project['labels'])
    w.task=object()
    try:
        w.update_controls();assert not w.undo_all_label_action.isEnabled()
        w.undo_all_labels();assert w.project['labels']==before
    finally:w.task=None;w.update_controls()
    w.select_label(identifier);w.begin_reshape();assert w.reshape_session is not None
    assert not w.undo_all_label_action.isEnabled()
    w.undo_all_labels();assert w.project['labels']==before
    w.cancel_reshape();assert not errors
