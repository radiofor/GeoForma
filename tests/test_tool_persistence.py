"""User tool choices survive editing, background refresh and workspace transitions."""
import copy
import pytest
from PySide6.QtCore import Qt,QEvent
from PySide6.QtGui import QFocusEvent,QKeyEvent
from PySide6.QtTest import QTest
from shapely.geometry import box,mapping
from geoforma.storage import save_project,load_project,project_snapshot
from test_workbench import workbench,fake_image
from test_project_loading import saved_project,wait_loading
from test_reshape import raster_image,workbench as reshape_workbench,OUT,prepare_preview


def ready_window(w):
    image=fake_image('image');image['ready']=True
    w.project['images']=[image];w.refresh_images();w.images.setCurrentRow(0)


def assert_tool(w,tool):
    assert w.view.mode==w.view.selected_mode==tool
    assert w.mode_actions[tool].isChecked()
    assert sum(action.isChecked() for action in w.mode_actions.values())==1


@pytest.mark.parametrize('tool',['positive','negative','box','select_points','select','pan','reshape'])
def test_save_label_and_history_keep_the_chosen_tool(workbench,tool):
    w,app,wait,errors=workbench;ready_window(w);w.set_tool(tool)
    w.draft={'geometry':mapping(box(100,100,140,140)),'points':[],'pending':False}
    w.refresh_labels();w.view.setFocus();app.processEvents()
    w.confirm_button.click()
    wait();assert len(w.project['labels'])==1 and not w.draft
    assert_tool(w,tool)
    w.refresh_labels();w.update_controls();assert_tool(w,tool)
    w.undo_label();wait();assert not w.project['labels'];assert_tool(w,tool)
    w.redo_label();wait();assert len(w.project['labels'])==1;assert_tool(w,tool)
    w.clear_draft();w.zoom_selected();w.view.fit_image();wait();assert_tool(w,tool)
    assert not errors






def test_space_does_not_change_tool_or_undo_a_new_explicit_choice(workbench):
    w,app,wait,errors=workbench;ready_window(w);w.set_tool('negative')
    QTest.keyPress(w.view,Qt.Key.Key_Space)
    assert w.view.mode=='negative' and w.view.selected_mode=='negative'
    assert w.mode_actions['negative'].isChecked()
    w.mode_actions['box'].trigger();assert_tool(w,'box')
    QTest.keyRelease(w.view,Qt.Key.Key_Space);assert_tool(w,'box')


def test_space_and_focus_loss_leave_selection_unchanged(workbench):
    w,app,wait,errors=workbench;ready_window(w);w.set_tool('negative')
    QTest.keyPress(w.view,Qt.Key.Key_Space)
    w.view.keyReleaseEvent(QKeyEvent(QEvent.Type.KeyRelease,Qt.Key.Key_Space,Qt.KeyboardModifier.NoModifier,' ',True))
    assert w.view.mode=='negative' and w.view.selected_mode=='negative'
    w.capture_workspace();assert w.project['workspace']['tool']=='negative'
    w.view.focusOutEvent(QFocusEvent(QEvent.Type.FocusOut));assert_tool(w,'negative')
    QTest.keyRelease(w.view,Qt.Key.Key_Space);assert_tool(w,'negative')


@pytest.mark.parametrize('recovering',[False,True])
def test_open_and_recovery_restore_the_saved_tool(workbench,saved_project,recovering):
    w,app,wait,errors=workbench;path,project=saved_project
    project['workspace'].update(tool='negative',tools={'individual':'negative'})
    save_project(project,path)
    w.set_tool('pan');assert w.request_project_open(path,recover_latest=recovering)
    wait_loading(w,app);wait();assert_tool(w,'negative')
    wait();assert_tool(w,'negative')
    assert not errors


def test_legacy_project_keeps_current_compatible_tool(workbench,saved_project):
    w,app,wait,errors=workbench;path,project=saved_project
    ready_window(w);w.set_tool('box')
    assert w.open_project(path);wait();assert_tool(w,'box')
    assert not errors


@pytest.mark.parametrize('tool',['pan','select','reshape'])
def test_saving_and_selecting_next_label_keep_tool(workbench,tool):
    w,app,wait,errors=workbench;ready_window(w)
    w.project['labels']=[dict(id=str(i),image_id='image',annotation_mode='individual',status='confirmed',class_id=1,
                              geometry=mapping(box(100+i*100,100,140+i*100,140)),window=[0,0,1024,1024]) for i in range(3)]
    w.refresh_labels();wait();w.set_tool(tool)
    w.select_label('0');w.edit_selected(locate=False);assert_tool(w,tool)
    w.confirm_button.click();wait();assert_tool(w,tool)
    assert next(l for l in w.project['labels'] if l['id']=='0')['status']=='confirmed' and not w.draft
    w.review_target();wait();assert_tool(w,tool)
    assert not errors


def test_switch_image_raw_view_and_temporary_busy_state_keep_tool(workbench):
    w,app,wait,errors=workbench;ready_window(w);w.set_tool('negative')
    w.project['images'].append(fake_image('unprepared','other.tif'));w.refresh_images()
    w.images.setCurrentRow(1);wait();assert_tool(w,'negative')
    assert not w.mode_actions['negative'].isEnabled()
    w.images.setCurrentRow(0);wait();assert_tool(w,'negative')
    for raw in (True,False):
        w.raw_view_action.setChecked(not raw);w.toggle_raw();wait();assert_tool(w,'negative')
    w.run('刷新后台',lambda task:None,lambda _:None,kind='bands');wait();assert_tool(w,'negative')
    assert not errors


def test_reopening_suspended_reshape_restores_pan_and_construction_line(reshape_workbench):
    w,app,tmp=reshape_workbench;w.begin_reshape();w.reshape_session['stroke']=copy.deepcopy(OUT)
    w.set_tool('pan');w.capture_workspace();path=tmp/'pan.gfm';save_project(w.project,path)
    w.cancel_reshape();assert w.open_project(path)
    assert_tool(w,'pan')
    assert w.reshape_session is not None and w.reshape_session['stroke']==OUT
    w.set_tool('reshape');assert_tool(w,'reshape')
    assert w.reshape_session['stroke']==OUT


@pytest.mark.parametrize('tool',['reshape','pan'])
def test_automatic_reshape_save_keeps_tool_and_does_not_start_another_edit(reshape_workbench,tool):
    w,app,tmp=reshape_workbench;prepare_preview(w);w.commit_reshape();w.set_tool(tool)
    assert not w.confirm_button.isEnabled() and not w.draft
    w.confirm_button.click()
    app.processEvents();assert_tool(w,tool)
    assert not w.draft and w.reshape_session is None and not w.view.reshape_points
    assert w.project['labels'][0]['editing_state']=='manual'
    w.undo_label();assert_tool(w,tool);w.redo_label();assert_tool(w,tool)


@pytest.mark.parametrize('tool',['positive','negative','box','select_points','select','pan','reshape'])
def test_manual_save_and_autosave_snapshot_keep_tool(workbench,tool):
    w,app,wait,errors=workbench;ready_window(w);w.set_tool(tool)
    w.save();wait();assert_tool(w,tool)
    assert load_project(w.project_path)['workspace']['tool']==tool
    snapshot=project_snapshot(w.project);automatic=w.project_path.with_name('snapshot.gfm')
    save_project(snapshot,automatic);assert_tool(w,tool)
    assert load_project(automatic)['workspace']['tools']['individual']==tool
    assert not errors


@pytest.mark.parametrize('damage',[{'tool':'erase'},{'operation':1,'tool':'erase'},{'tools':{'automatic':'erase'}},{'tools':[]},{'tools':{'other':'pan'}}])
def test_invalid_persisted_tool_is_rejected_before_commit(saved_project,damage):
    path,project=saved_project;project=copy.deepcopy(project);project['workspace'].update(damage)
    save_project(project,path)
    with pytest.raises(ValueError,match='工具|标注模式'):load_project(path)


@pytest.mark.parametrize('tool',['positive','negative','box','select_points'])
def test_removed_automatic_mode_is_rejected(saved_project,tool):
    path,project=saved_project;project=copy.deepcopy(project)
    project['workspace'].update(operation=1,tool=tool,tools={'automatic':tool})
    save_project(project,path)
    with pytest.raises(ValueError,match='标注模式'):load_project(path)
