import os,copy,time
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtCore import QSettings,Qt,QRectF,QEvent
from PySide6.QtWidgets import QApplication,QPushButton,QToolButton
from shapely.geometry import box,mapping
from geoforma.window import MainWindow
from geoforma.workflow import fully_prepared
from geoforma.storage import project_snapshot


@pytest.fixture
def workbench(tmp_path):
    app=QApplication.instance() or QApplication([]);w=MainWindow(auto_prepare=False);w.settings=QSettings('GeoForma','GeoFormaTests');w.project_path=tmp_path/'workbench.gfm';w.autosave=lambda:None;w.request_render=lambda *a:None;w.autosave_timer.stop();w.show();app.processEvents();w.render_timer.stop()
    w.auto_apply.setChecked(False)
    errors=[];w.error=errors.append
    def wait():
        start=time.monotonic();settled=0
        while settled<3:
            app.processEvents();time.sleep(.005)
            active=w.task or w.label_index_task or w.render_task or w.render_timer.isActive() or w.autosave_task or (w.auto_prepare and w.preparation.ids and not w.preparation.paused)
            settled=0 if active else settled+1
            if time.monotonic()-start>10:raise TimeoutError(errors)
    yield w,app,wait,errors
    w.auto_prepare=False;w.preparation.reset();w.project_saves.pending.clear();w.project_saves.failed.clear();w.dirty=False;w.close();wait()
    deadline=time.monotonic()+10
    while not getattr(w,'shutdown_complete',False):
        app.processEvents();time.sleep(.005)
        if time.monotonic()>deadline:raise TimeoutError('Workbench shutdown did not complete')
    w.deleteLater();app.sendPostedEvents(None,QEvent.Type.DeferredDelete);app.processEvents()


def fake_image(identifier,path='one.tif'):
    return {'id':identifier,'path':path,'name':path,'width':2000,'height':2000,'ready':False,'model_recipe':{'bands':[1,2,3]},
            'display_recipe':None,'suggested_bands':[1,2,3],'fingerprint':identifier,'bands':3,'dtypes':['uint8'],'crs':'EPSG:3857','source_files':1,'transform':[1,0,0,0,-1,0]}


def populate(w,wait):
    im=fake_image('one');im['ready']=True;w.project['images']=[im];w.refresh_images();w.images.setCurrentRow(0)
    w.project['labels']=[{'id':str(i),'image_id':'one','class_id':1,'status':'confirmed','geometry':mapping(box(x,100,x+80,180)),
                          'score':.9,'window':[-128,-128,1024,1024],'edge':False,'source':'automatic'} for i,x in enumerate([100,400,700])]
    w.refresh_labels();wait();return im


def test_import_prepares_only_current_and_next_image_in_order(workbench,monkeypatch):
    w,app,wait,errors=workbench;w.auto_prepare=True;calls=[]
    import PySide6.QtWidgets as ui
    from geoforma.controllers import images as image_flow
    monkeypatch.setattr(image_flow,'inspect_source',lambda path:fake_image(path,path));monkeypatch.setattr(image_flow,'make_recipe',lambda *a:{'bands':[1,2,3],'ranges':[[0,255]]*3})
    def prep(im,config,bounds,task):
        calls.append((im['id'],bounds));return {'count':9,'hits':9,'checkpoint':config['checkpoint'],'device':'cpu','execution':'native'}
    w.service.preprocess=prep;w.view.fitInView(QRectF(800,800,10,10),Qt.AspectRatioMode.KeepAspectRatio)
    w.import_paths(['one.tif','two.tif','three.tif','four.tif']);wait()
    from pathlib import Path
    assert calls==[(str(Path(name).resolve()),[0,0,2000,2000]) for name in ('one.tif','two.tif')]
    assert [fully_prepared(im,w.project['model']) for im in w.project['images']]==[True,True,False,False] and not errors
    assert not hasattr(w,'scope')


def test_individual_saved_label_edit_reset_and_confirmation(workbench):
    w,app,wait,errors=workbench;populate(w,wait)
    w.project["labels"]=[dict(w.project["labels"][0],status="confirmed",class_id=1,annotation_mode="individual"),*w.project["labels"][1:]]
    wait();original=copy.deepcopy(w.project["labels"]);requests=[]
    def predict(im,config,request,task):
        requests.append(copy.deepcopy(request));return {"choices":[{"geometry":mapping(box(100,100,182,181)),"score":.91,"edge":False}],"window":request["window"],"key":"test","cache_hit":True,"device":"cpu"}
    w.service.predict=predict;w.select_label("0");w.edit_selected(locate=False);w.add_point(140,140,1)
    w.predict();wait();assert requests[-1]["seed"]==original[0]["geometry"]
    w.reset_prior();wait();assert requests[-1]["seed"] is None
    w.clear_draft();wait();assert w.project["labels"]==original
    w.select_label("0");w.edit_selected(locate=False);w.add_point(140,140,1);w.predict();wait();w.confirm();wait()
    assert next(l for l in w.project["labels"] if l["id"]=="0")["annotation_mode"]=="individual"
    assert not w.draft and len(w.project["labels"])==3
    w.undo_label();wait();assert w.project["labels"]==original
    w.redo_label();wait();assert not errors


def test_review_navigation_includes_active_candidate(workbench):
    w,app,wait,errors=workbench;populate(w,wait)
    w.select_items('labels',['1']);w.review_target(1);assert w.selected_id=='2' and not w.draft
    w.review_target(-1);assert w.selected_id=='1' and not w.draft
    w.add_point(440,140,1);w.review_target(1);assert w.selected_id=='0' and w.draft['points']==[[440,140,1]]
    w.clear_draft();w.select_label('1');w.edit_selected();w.review_target(1);assert w.selected_id=='0' and w.draft['base_id']=='1' and not w.draft['points']


def test_category_change_is_staged_and_saved_without_model_inference(workbench):
    w,app,wait,errors=workbench;populate(w,wait)
    w.project['classes'].append({'id':2,'name':'道路'});w.refresh_classes()
    w.select_label('0');w.edit_selected();geometry=copy.deepcopy(w.draft['geometry'])
    w.classes.setCurrentIndex(w.classes.findData(2));assert w.draft_modified()
    w.review_target(1);assert w.draft['base_id']=='0'
    assert w.confirm_button.isEnabled() and not w.apply_button.isEnabled()
    w.confirm();wait()
    label=next(l for l in w.project['labels'] if l['id']=='0')
    assert label['class_id']==2 and label['geometry']==geometry and label['status']=='confirmed'
    assert not errors






def test_small_window_can_scroll_to_every_operation(workbench):
    w,app,wait,errors=workbench;populate(w,wait);w.select_items('labels',['1']);w.draft['edge']=True;w.update_draft_info();w.update_controls();w.resize(1024,700);app.processEvents()
    w.editor_scroll.ensureWidgetVisible(w.next_button);app.processEvents()
    bottom=w.next_button.mapTo(w.editor_scroll.viewport(),w.next_button.rect().bottomRight())
    assert w.editor_scroll.viewport().rect().contains(bottom)
    for a in [w.delete_action,w.undo_prompt_action,w.raw_view_action]:
        toolbar=next(parent for parent in w.findChildren(__import__('PySide6.QtWidgets',fromlist=['QToolBar']).QToolBar) if parent.widgetForAction(a))
        button=toolbar.widgetForAction(a);assert button.isVisible() and toolbar.rect().contains(button.geometry().bottomRight())


def test_deleted_label_can_be_undone_and_redone(workbench):
    w,app,wait,errors=workbench;populate(w,wait);original=copy.deepcopy(w.project['labels'])
    w.select_items('labels',['1']);w.delete_selected();wait()
    w.refresh_labels();wait();assert {l['id'] for l in w.project['labels']}=={'0','2'}
    w.undo_label();wait();assert {l['id'] for l in w.project['labels']}=={'0','1','2'}
    w.redo_label();wait();assert {l['id'] for l in w.project['labels']}=={'0','2'}


def test_delete_keeps_no_next_target_and_context_undo(workbench):
    w,app,wait,errors=workbench;populate(w,wait);w.select_items('labels',['1']);w.delete_selected();wait()
    assert not w.draft and w.undo_prompt_action.isEnabled()
    w.undo_context();wait();assert not w.draft and {l['id'] for l in w.project['labels']}=={'0','1','2'}
    w.redo_context();wait();assert {l['id'] for l in w.project['labels']}=={'0','2'}


def test_switch_images_keeps_separate_pending_prompts_and_history(workbench):
    w,app,wait,errors=workbench;populate(w,wait);other=fake_image('two','two.tif');other['ready']=True;w.project['images'].append(other);w.refresh_images()
    w.add_point(230,240,1);w.add_point(260,270,0);before=copy.deepcopy(w.draft)
    w.images.setCurrentRow(1);assert not w.draft;w.add_point(400,500,1)
    w.images.setCurrentRow(0);assert w.draft==before;w.undo_prompt();assert w.draft['points']==[[230,240,1]]
    w.images.setCurrentRow(1);assert w.draft['points']==[[400,500,1]]


def test_raw_view_prevents_hidden_prompt_editing_and_buttons_are_short(workbench):
    w,app,wait,errors=workbench;populate(w,wait);w.raw_view_action.setChecked(False);w.toggle_raw();w.add_point(100,100,1)
    assert not w.draft and all(not item.isVisible() for item in w.view.overlay_items)
    w.raw_view_action.setChecked(True);w.toggle_raw();w.add_point(100,100,1);assert len(w.draft['points'])==1
    for button in w.findChildren(QPushButton)+w.findChildren(QToolButton):
        if button.isVisible():assert not any(token in button.text().lower() for token in ['ctrl','enter','shift'])


def test_eye_has_two_status_presentations_for_mouse_and_workspace(workbench):
    from PySide6.QtTest import QTest
    w,app,wait,errors=workbench;populate(w,wait)
    button=w.visibility_toolbar.widgetForAction(w.raw_view_action)
    assert not button.isCheckable() and button.property('visibilityState')=='visible' and w.raw_view_action.isChecked() and w.view.overlay_visible
    assert '已显示' in button.toolTip()
    QTest.mouseClick(button,Qt.MouseButton.LeftButton)
    assert not button.isCheckable() and button.isEnabled() and button.property('visibilityState')=='hidden' and not w.raw_view_action.isChecked() and not w.view.overlay_visible
    assert '已隐藏' in button.toolTip()
    w.capture_workspace();assert w.project['workspace']['raw_view'] is True
    QTest.keyClick(w,Qt.Key.Key_Tab);app.processEvents();assert not w.raw_view_action.isChecked()
    QTest.mouseClick(button,Qt.MouseButton.LeftButton)
    assert not button.isCheckable() and button.property('visibilityState')=='visible' and w.raw_view_action.isChecked() and w.view.overlay_visible
    assert '已显示' in button.toolTip()
    w.capture_workspace();assert w.project['workspace']['raw_view'] is False and not errors


def test_storage_snapshot_detaches_mutable_project_records(workbench):
    w,app,wait,errors=workbench;populate(w,wait);w.capture_workspace();snapshot=project_snapshot(w.project)
    w.project['model']['device']='cpu';w.image['candidate_runs']={'new':{'complete':True}};w.project['labels'][0]['class_id']=2;w.project['labels'].pop()
    assert snapshot['model']['device']=='cuda' and 'candidate_runs' not in snapshot['images'][0]
    assert len(snapshot['labels'])==3 and snapshot['labels'][0]['class_id']==1


def test_preparation_pause_stops_queue_and_resume_keeps_other_images(workbench):
    w,app,wait,errors=workbench;w.auto_prepare=True;images=[fake_image('one'),fake_image('two','two.tif')];w.project['images']=images;w.refresh_images();w.images.setCurrentRow(0);attempts=[]
    def prep(im,config,bounds,task):
        attempts.append(im['id'])
        if len(attempts)==1:
            for _ in range(200):task.check();time.sleep(.005)
        return {'count':9,'hits':9,'checkpoint':config['checkpoint'],'device':'cpu','execution':'native'}
    w.service.preprocess=prep;w.queue_preparation()
    until=time.monotonic()+3
    while not w.task:app.processEvents();time.sleep(.005);assert time.monotonic()<until
    w.cancel();wait();assert w.preparation.paused and not any(im['ready'] for im in images) and not errors
    assert w.progress.model.state.phase=='cancelled' and w.last_error
    errors.clear();w.preprocess();wait();assert attempts==['one','one','two'] and all(im['ready'] for im in images) and not errors


def test_async_autosave_does_not_clear_newer_edits(workbench,monkeypatch):
    w,app,wait,errors=workbench;populate(w,wait)
    import PySide6.QtWidgets as ui
    from geoforma.storage import save_project,load_project
    save_project(w.project,w.project_path)
    def slow_save(project,path,**kwargs):time.sleep(.08);save_project(project,path,**kwargs)
    monkeypatch.setattr('geoforma.controllers.projects.save_project',slow_save)
    w.autosave=MainWindow.autosave.__get__(w);w.mark_dirty();w.autosave();w.project['classes'].append({'id':4,'name':'冰雪'});w.mark_dirty()
    # Keep the debounce from saving the newer edit before the first write settles.
    w.autosave_debounce.stop()
    wait();assert w.dirty
    w.autosave();wait();assert not w.dirty
    assert load_project(w.project_path)['classes'][-1]['name']=='冰雪'


def test_close_aborts_when_autosave_cannot_write(workbench,monkeypatch):
    w,app,wait,errors=workbench;populate(w,wait)
    import PySide6.QtWidgets as ui
    warnings=[]
    def fail_save(*args,**kwargs):raise OSError('disk full')
    monkeypatch.setattr('geoforma.controllers.projects.save_project',fail_save);monkeypatch.setattr(ui.QMessageBox,'warning',lambda *a:warnings.append(a))
    w.autosave=MainWindow.autosave.__get__(w);w.mark_dirty();w.close();wait()
    assert w.isVisible() and not w.closing and w.dirty and warnings


def test_panel_shows_selected_model_and_actual_cpu_fallback(workbench):
    w,app,wait,errors=workbench;populate(w,wait)
    w.project['model'].update(backend='sam2.1',variant='small',device='cuda',execution='native')
    w.record_runtime({'device':'cpu'});w.update_controls();w.refresh_info()
    assert w.model_button.isVisible() and w.model_button.text()=='SAM 2.1 · Small'
    assert w.model_runtime.text()=='设备：CPU（回退）'
    assert '模型 RGB：1/2/3' in w.image_info.text() and 'GPKG/SHP CRS' not in w.image_info.text()
    assert w.export_crs_input.text()=='EPSG:3857'
    w.project['model']['variant']='tiny';w.update_controls();assert w.model_runtime.text()=='设备：GPU 优先 · 待加载'
