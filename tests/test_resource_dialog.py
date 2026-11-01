from PySide6.QtCore import Qt
from geoforma.ui.resources import ResourceDialog
from geoforma import native_runtime
from test_workbench import workbench


def test_resource_location_choice_and_reset(workbench,monkeypatch,tmp_path):
    from pathlib import Path
    from geoforma import resource_location,resource_migration
    from geoforma.ui import resources
    w,app,wait,errors=workbench
    state={'path':tmp_path/'default'};closed=[]
    monkeypatch.setattr(resource_location,'current_resource_dir',lambda *args:state['path'])
    monkeypatch.setattr(resource_location,'require_resource_dir',lambda *args:state['path'])
    def change(parent,task):
        old=state['path'];state['path']=Path(parent)/'GeoForma-Resources';return {'source':str(old),'destination':str(state['path'])}
    def reset(task):
        old=state['path'];state['path']=tmp_path/'default';return {'source':str(old),'destination':str(state['path'])}
    monkeypatch.setattr(resource_migration,'migrate_resources',change)
    monkeypatch.setattr(resource_migration,'migrate_to_default',reset)
    monkeypatch.setattr(resources.QFileDialog,'getExistingDirectory',lambda *args:str(tmp_path/'drive'))
    monkeypatch.setattr(w.service,'close',lambda:closed.append(True))
    dialog=ResourceDialog(w);dialog.location_choose.click();wait()
    assert dialog.location_path.text()==str(tmp_path/'drive'/'GeoForma-Resources')
    assert closed==[True] and w.preparation.paused
    assert '资源迁移完成' in dialog.details.toPlainText()
    dialog.location_reset.click();wait()
    assert dialog.location_path.text()==str(tmp_path/'default') and len(closed)==2
    dialog.accept();dialog.deleteLater();assert not errors


def test_resource_location_change_is_disabled_during_cleanup(workbench,monkeypatch):
    w,app,wait,errors=workbench;dialog=ResourceDialog(w)
    w.housekeeping_task=object();dialog.sync_busy()
    assert not dialog.location_choose.isEnabled() and not dialog.location_reset.isEnabled()
    w.housekeeping_task=None;dialog.sync_busy();assert dialog.location_choose.isEnabled()
    w.autosave_task=object();dialog.sync_busy()
    assert not dialog.location_choose.isEnabled() and not dialog.location_reset.isEnabled()
    w.autosave_task=None;dialog.sync_busy();assert dialog.location_choose.isEnabled()
    dialog.accept();dialog.deleteLater();assert not errors


def test_migration_saves_dirty_work_before_starting(workbench,monkeypatch,tmp_path):
    from geoforma import resource_migration
    w,app,wait,errors=workbench;calls=[]
    w.dirty=True;w.project_path=tmp_path/'project.geoforma.json'
    monkeypatch.setattr(w,'autosave',lambda:calls.append('autosave'))
    monkeypatch.setattr(resource_migration,'migrate_resources',lambda *args:calls.append('migrate'))
    dialog=ResourceDialog(w);dialog.change_location(tmp_path)
    assert calls==['autosave'] and w.dirty and dialog.task is None
    assert '保存' in dialog.phase.text()
    dialog.accept();dialog.deleteLater();w.dirty=False;assert not errors


def test_interrupted_migration_blocks_resource_changes_and_can_resume(workbench,monkeypatch,tmp_path):
    from geoforma import resource_migration
    w,app,wait,errors=workbench;state={'pending':True};calls=[]
    monkeypatch.setattr(resource_migration,'pending_migration',lambda:{'source':'old','destination':'new'} if state['pending'] else None)
    def resume(task):
        calls.append(True);task.signals.progress.emit(1,2,'复制资源');state['pending']=False
        return {'source':str(tmp_path/'old'),'destination':str(tmp_path/'new')}
    monkeypatch.setattr(resource_migration,'resume_migration',resume)
    dialog=ResourceDialog(w);dialog.show();app.processEvents()
    assert dialog.resume_migration_button.isVisible() and dialog.resume_migration_button.isEnabled()
    assert not dialog.location_choose.isEnabled() and not dialog.weight_download.isEnabled()
    dialog.resume_migration_button.click();wait()
    assert calls==[True] and not dialog.resume_migration_button.isVisible()
    assert dialog.location_choose.isEnabled() and not errors
    dialog.accept();dialog.deleteLater()


def test_resource_switch_busy_destination_does_not_change_saved_location(workbench,monkeypatch,tmp_path):
    from geoforma.resource_location import current_resource_dir,prepare_resource_parent,require_resource_dir
    from geoforma.session_guard import ResourceLease,resource_session
    from geoforma.ui import resources
    w,app,wait,errors=workbench
    root=tmp_path/'data';root.mkdir();monkeypatch.setenv('GEOFORMA_DATA_DIR',str(root))
    parent=tmp_path/'other';parent.mkdir();target=prepare_resource_parent(parent)
    busy=ResourceLease();busy.ensure(target);messages=[]
    monkeypatch.setattr(resources.QMessageBox,'warning',lambda *args:messages.append(args[-1]))
    try:
        with resource_session() as active:
            assert require_resource_dir()==root
            dialog=ResourceDialog(w);dialog.change_location(parent);wait()
            assert current_resource_dir()==root and active.root==root.resolve()
            assert '另一个' in dialog.details.toPlainText()
            dialog.accept();dialog.deleteLater()
    finally:busy.close()
    assert not errors


def test_unavailable_resource_location_can_be_reset(workbench,monkeypatch,tmp_path):
    from geoforma import resource_location,resource_migration
    w,app,wait,errors=workbench
    state={'valid':False}
    def current(*args):
        return tmp_path
    def require(*args):
        if not state['valid']:raise ValueError('资源目录不可访问')
        return tmp_path
    def reset(task):state['valid']=True;return {'source':str(tmp_path),'destination':str(tmp_path)}
    monkeypatch.setattr(resource_location,'current_resource_dir',current)
    monkeypatch.setattr(resource_location,'require_resource_dir',require)
    monkeypatch.setattr(resource_migration,'migrate_to_default',reset)
    monkeypatch.setattr(w.service,'close',lambda:None)
    dialog=ResourceDialog(w);assert '不可用' in dialog.location_path.text()
    assert not dialog.weight_download.isEnabled() and dialog.location_reset.isEnabled()
    dialog.location_reset.click();wait()
    assert dialog.location_path.text()==str(tmp_path) and dialog.weight_download.isEnabled()
    dialog.accept();dialog.deleteLater();assert not errors


def test_migration_reconciles_ready_signature_off_gui_thread(workbench,monkeypatch,tmp_path):
    import copy,threading
    from geoforma import cache_recovery
    w,app,wait,errors=workbench;dialog=ResourceDialog(w);root=tmp_path/'destination'
    (root/'cache').mkdir(parents=True)
    (root/'cache'/'active-project.json').write_text('{"owner":"'+w.project['cache_id']+'","revision":"abc"}')
    project=copy.deepcopy(w.project);project['images']=[{'id':'one','prepared_full_signature':'old'}];threads=[]
    monkeypatch.setattr(cache_recovery,'remap_migrated_checkpoint',lambda value:True)
    def reconcile(value,path,revision,task):
        threads.append(threading.current_thread().ident);value['images'][0]['prepared_full_signature']='verified'
    monkeypatch.setattr(cache_recovery,'reconcile_prepared',reconcile)
    results=[];gui_thread=threading.current_thread().ident
    worker=threading.Thread(target=lambda:results.append(dialog.migration_work(type('T',(),{})(),project,lambda:{'source':str(tmp_path/'old'),'destination':str(root)})))
    worker.start();worker.join()
    assert results[0]['reconciled_project']['images'][0]['prepared_full_signature']=='verified' and threads and threads[0]!=gui_thread
    dialog.accept();dialog.deleteLater();assert not errors

def test_settings_dialog_fixed_progress_layout_and_missing_resources_do_not_block_exports(workbench,monkeypatch):
    w,app,wait,errors=workbench
    monkeypatch.setattr(native_runtime,'lightweight',lambda:True)
    monkeypatch.setattr(native_runtime,'managed_runtime',lambda:None)
    w.update_controls();app.processEvents()
    assert w.model_runtime.text()=='设备：GPU 优先 · 资源未配置'
    assert '…' not in w.model_runtime._display_text
    assert 'GPU' in w.model_runtime._display_text and any(text in w.model_runtime._display_text for text in ('资源未配置','缺资源'))
    assert w.model_runtime.accessibleName()==w.model_runtime.text()
    assert '设置 → 资源配置' in w.model_runtime.toolTip()
    previous=w.model_runtime.setText;transitions=[]
    def track(text):
        if text!=w.model_runtime.text():transitions.append(text)
        previous(text)
    monkeypatch.setattr(w.model_runtime,'setText',track)
    w.update_controls();w.update_controls();assert not transitions
    w.configure_resources();app.processEvents();dialog=w.resource_dialog
    assert dialog is not None and dialog.isVisible() and dialog.model.count()>0
    assert not dialog.details.placeholderText() and not dialog.details.toPlainText()
    assert dialog.details.accessibleName()=='配置记录'
    initial=(dialog.size(),dialog.model.geometry(),dialog.details.geometry())
    dialog.progress.model.begin('test','resources')
    dialog.report(39,100,'运行库 1/2 · 下载 torch · 39 / 100 MiB');app.processEvents()
    assert '39%' in dialog.phase.text() and initial==(dialog.size(),dialog.model.geometry(),dialog.details.geometry())
    dialog.progress.model.finish('complete');assert dialog.progress.phase=='complete'
    app.processEvents()
    assert initial==(dialog.size(),dialog.model.geometry(),dialog.details.geometry())
    dialog.accept();app.processEvents();assert w.resource_dialog is None
    assert not w.project_actions['save'].isEnabled() and not errors

def test_inference_gate_keeps_tool_and_pauses_queue_without_starting_worker(workbench,monkeypatch):
    w,app,wait,errors=workbench
    monkeypatch.setattr(native_runtime,'lightweight',lambda:True)
    monkeypatch.setattr(native_runtime,'managed_runtime',lambda:None)
    w.resource_reminded=True;w.set_tool('positive');before=w.mode_actions['positive'].isChecked()
    assert not w.run('predict',lambda task:None,lambda _:None,kind='interactive')
    assert w.task is None and w.preparation.paused and w.mode_actions['positive'].isChecked()==before

def test_new_missing_resource_reminds_again_after_a_successful_configuration(workbench,monkeypatch):
    from geoforma.controllers import resources
    w,app,wait,errors=workbench;monkeypatch.setattr(native_runtime,'lightweight',lambda:True)
    monkeypatch.setattr(resources,'snapshot',lambda config:dict(ready=True))
    w.resource_reminded=True;assert w.ensure_model_resources() and not w.resource_reminded
    queued=[];monkeypatch.setattr(resources.QTimer,'singleShot',lambda delay,callback:queued.append(callback))
    monkeypatch.setattr(resources,'snapshot',lambda config:dict(ready=False))
    assert not w.ensure_model_resources() and len(queued)==1
    assert not w.ensure_model_resources() and len(queued)==1


def test_bundled_runtime_still_prompts_for_missing_model_weight(workbench,monkeypatch):
    from types import SimpleNamespace
    from geoforma.controllers import resources
    w,app,wait,errors=workbench
    monkeypatch.setattr(resources,'sys',SimpleNamespace(frozen=True))
    monkeypatch.setattr(native_runtime,'lightweight',lambda:False)
    monkeypatch.setattr(resources,'snapshot',lambda config:dict(ready=False))
    queued=[];monkeypatch.setattr(resources.QTimer,'singleShot',lambda delay,callback:queued.append(callback))
    w.resource_reminded=False
    assert not w.ensure_model_resources() and w.preparation.paused and len(queued)==1
    assert not w.ensure_model_resources() and len(queued)==1


def test_lightweight_dialog_configures_selected_runtime_and_manual_import(workbench,monkeypatch):
    from geoforma.ui import resources
    w,app,wait,errors=workbench
    monkeypatch.setattr(native_runtime,'lightweight',lambda:True)
    monkeypatch.setattr(native_runtime,'managed_runtime',lambda:None)
    dialog=ResourceDialog(w);calls=[]
    assert [dialog.tabs.tabText(i) for i in range(dialog.tabs.count())]==['PyTorch 运行库','模型权重']
    monkeypatch.setattr(dialog,'run',lambda title,work,**kwargs:calls.append((title,work,kwargs)))
    installed=[]
    monkeypatch.setattr(native_runtime.NativeRuntimeManager,'install',lambda self,key,task,sources=None:installed.append((key,sources)))
    dialog.profile.setCurrentIndex(dialog.profile.findData('cu126'))
    dialog.install_runtime();calls[-1][1](None)
    assert installed[-1]==('cu126',None) and calls[-1][2]['reset_model'] is True
    monkeypatch.setattr(resources.QFileDialog,'getOpenFileNames',lambda *args:(['local.whl'],'Python wheel (*.whl)'))
    monkeypatch.setattr(resources,'dialog_result',lambda dialog:(True,None))
    dialog.runtime_manual.click();calls[-1][1](None)
    assert installed[-1]==('cu126',['local.whl']) and not errors
    dialog.accept();dialog.deleteLater()

def test_weight_and_cache_operations_keep_the_resident_model(workbench,monkeypatch):
    w,app,wait,errors=workbench;closed=[];monkeypatch.setattr(w.service,'close',lambda:closed.append(True))
    monkeypatch.setattr(native_runtime.NativeRuntimeManager,'clear_downloads',lambda *args:dict(removed_bytes=0,files=0))
    dialog=ResourceDialog(w);dialog.clear_cache_action.trigger();wait()
    assert not closed and dialog.progress.phase=='complete' and not errors
    assert dialog.phase.text()=='缓存已清理' and '配置完成' not in dialog.details.toPlainText()
    dialog.accept();dialog.deleteLater()

def test_startup_reminder_defers_during_restore_without_marking_it_shown(workbench,monkeypatch):
    from geoforma.controllers import resources
    w,app,wait,errors=workbench;monkeypatch.setattr(native_runtime,'lightweight',lambda:True)
    monkeypatch.setattr(resources,'snapshot',lambda config:dict(ready=False))
    opened=[];monkeypatch.setattr(w,'configure_resources',lambda:opened.append(True))
    w.resource_reminded=False;w.loading_task=object()
    try:w.remind_resources();assert not opened and not w.resource_reminded
    finally:w.loading_task=None
    w.remind_resources();assert opened==[True] and w.resource_reminded


def test_manual_import_is_available_before_any_download(workbench,monkeypatch):
    from geoforma.ui import resources
    w,app,wait,errors=workbench
    dialog=ResourceDialog(w);calls=[]
    monkeypatch.setattr(resources.QFileDialog,'getOpenFileName',lambda *args:('local.pt','模型权重 (*.pt *.pth)'))
    monkeypatch.setattr(dialog,'install_weight',lambda path:calls.append(('weight',path)))
    monkeypatch.setattr(resources,'dialog_result',lambda dialog:(True,None))
    assert dialog.weight_manual.isEnabled()
    dialog.weight_manual.click()
    assert calls==[('weight','local.pt')]
    assert dialog.progress.phase=='idle' and not errors
    dialog.accept();dialog.deleteLater()


def test_download_links_include_official_home_and_exact_files():
    from geoforma.resource_links import PYTORCH_HOME,SAM_HOME,SAM2_HOME,model_home,download_html,download_text
    from geoforma.model_catalog import MODELS
    from geoforma.weights import checkpoint_resource
    for key in native_runtime.catalog()['profiles']:
        files=native_runtime.download_wheels(key)
        page=download_html(files,PYTORCH_HOME);text=download_text(files,PYTORCH_HOME)
        assert PYTORCH_HOME in page and PYTORCH_HOME in text
        for item in files:
            assert item['url'] not in page and item['url'] in text and item['sha256'].upper() in page
    for spec in MODELS:
        home=model_home(spec)
        expected='https://huggingface.co/1038lab/sam3/tree/main' if spec['backend']=='sam3' else SAM_HOME if spec['backend']=='sam' else SAM2_HOME
        assert home==expected
        item=checkpoint_resource(spec);assert item['url'] in download_text([item],home)


def test_resource_error_shows_reason_and_allows_direct_retry(workbench):
    w,app,wait,errors=workbench;dialog=ResourceDialog(w)
    def invalid(task):raise ValueError('文件校验失败，请选择官方文件。')
    dialog.run('导入权重',invalid);wait()
    assert dialog.progress.phase=='failed' and dialog.task is None
    assert dialog.details.toPlainText()=='文件校验失败，请选择官方文件。'
    assert dialog.weight_manual.isEnabled()
    assert 'ValueError' in w.log.toPlainText() and not errors
    dialog.accept();dialog.deleteLater()


def test_manual_configuration_uses_official_home_and_distinguishes_import_from_close(workbench,monkeypatch):
    from geoforma.ui import resource_manual
    from geoforma.resource_links import PYTORCH_HOME
    w,app,wait,errors=workbench;opened=[]
    monkeypatch.setattr(resource_manual.QDesktopServices,'openUrl',lambda url:opened.append(url.toString()) or True)
    dialog=resource_manual.ManualResourceDialog(w,native_runtime.download_wheels('cpu'),PYTORCH_HOME)
    dialog.website.click();assert opened==[PYTORCH_HOME]
    dialog.import_button.click();assert dialog.result()==dialog.DialogCode.Accepted
    dialog.reject();assert dialog.result()==dialog.DialogCode.Rejected
    dialog.deleteLater();assert not errors


def test_manual_configuration_caption_names_selected_model(workbench):
    from geoforma.ui.resource_manual import ManualResourceDialog
    from geoforma.model_catalog import model_spec
    from geoforma.weights import checkpoint_resource
    from geoforma.resource_links import model_home
    w,app,wait,errors=workbench;spec=model_spec('large','sam2.1')
    dialog=ManualResourceDialog(w,[checkpoint_resource(spec)],model_home(spec),'模型权重 · '+spec['title'])
    assert 'Large' in dialog.windowTitle() and 'large' in dialog.browser.toPlainText()
    assert 'small' not in dialog.browser.toPlainText()
    dialog.reject();dialog.deleteLater();assert not errors
