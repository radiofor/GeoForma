"""Background project staging and a single signal-blocked workbench commit."""
import copy,traceback,threading
from contextlib import contextmanager
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,QSignalBlocker,QRectF
from PySide6.QtWidgets import QMessageBox,QFileDialog
from ..tasks import Task
from ..domain import data_dir
from ..domain import digest
from ..workbench_state import WorkbenchState
from ..project_loading import prepare_project
from ..ui.text import ui_text


@contextmanager
def blocked_controls(window):
    names=('images','classes','auto_apply','single_polygon',
           'smooth_enabled','smooth_value','raw_view_action','view')
    blockers=[QSignalBlocker(getattr(window,name)) for name in names]
    updates=window.updatesEnabled();window.setUpdatesEnabled(False)
    try:yield
    finally:
        for blocker in reversed(blockers):blocker.unblock()
        window.setUpdatesEnabled(updates)


class ProjectLoadingWorkflow:
    def resolve_missing_project_sources(self,project):
        from ..missing_sources import missing_sources,relink_source,remove_source
        changed=False
        for kind,source in missing_sources(project):
            while True:
                name=source.get('name') or Path(source['path']).name
                detail=('移除影像将同时移除其标注，并清除项目的撤销和重做记录。' if kind=='images' else '移除参考影像不会删除磁盘上的文件。')
                box=QMessageBox(QMessageBox.Icon.Warning,'找不到数据',f'{name}\n原路径：{source["path"]}\n\n{detail}',parent=self)
                locate=box.addButton('选择新位置',QMessageBox.ButtonRole.AcceptRole)
                remove=box.addButton('从项目移除',QMessageBox.ButtonRole.DestructiveRole)
                box.addButton('取消打开',QMessageBox.ButtonRole.RejectRole);box.exec()
                if box.clickedButton()==locate:
                    path,_=QFileDialog.getOpenFileName(self,'选择数据的新位置',str(Path(source['path']).parent),'影像文件 (*.tif *.tiff *.vrt *.img);;所有文件 (*)')
                    if not path:continue
                    try:relink_source(source,path,project,kind)
                    except Exception as error:QMessageBox.warning(self,'无法使用所选数据',str(error));continue
                    changed=True;break
                if box.clickedButton()==remove:
                    if QMessageBox.question(self,'确认移除',f'确定从项目移除“{name}”吗？\n{detail}')!=QMessageBox.StandardButton.Yes:continue
                    remove_source(project,kind,source);changed=True;break
                return None
        return changed

    def request_project_open(self,path,recover_latest=False):
        if self.task or self.reshape_session is not None or self.loading_task or self.project_transition or self.closing:return False
        from ..resource_migration import pending_migration
        try:pending=bool(pending_migration())
        except (OSError,ValueError,RuntimeError):pending=True
        if pending:
            self.statusBar().showMessage('请先完成资源迁移，再打开项目。',6000);return False
        try:
            if self.autosave() is False:return False
            actual=Path(path)
        except Exception:self.error(traceback.format_exc());return False
        self.auto_apply_timer.stop();self.render_timer.stop()
        if self.label_index_task:self.label_index_task.cancel()
        from ..ui.project_transition import ProjectTransition
        self.project_transition=ProjectTransition(self,recover_latest)
        size=(self.view.viewport().width(),self.view.viewport().height())
        def work(task):
            from ..resource_location import require_resource_dir
            self.wait_for_project_saves(task)
            root=require_resource_dir()
            from ..storage import load_project
            from ..missing_sources import missing_sources
            project=load_project(actual);changed=False
            if missing_sources(project):
                event=threading.Event();answer={'changed':None}
                task.signals.preview.emit((project,event,answer))
                while not event.wait(.05):task.check()
                task.check()
                if answer['changed'] is None:task.cancel();task.check()
                changed=answer['changed']
            if changed:
                from ..missing_sources import validate_resolved_project
                validate_resolved_project(project)
            loaded=prepare_project(actual,size,task,project=project)
            loaded.sources_changed=changed
            task.check();task.signals.progress.emit(0,0,'清理旧项目的影像缓存…')
            loaded.cache_cleared=self.service.activate_project(root,loaded.project['cache_id'])
            if not loaded.cache_cleared:
                task.signals.progress.emit(0,0,'核对已准备影像缓存…')
                from ..cache_recovery import reconcile_prepared
                loaded.reconciled_caches=reconcile_prepared(loaded.project,root,self.service.cache_revision,task)
            task.check();return loaded
        task=Task(work);self.loading_task=task;committed=False;settled=False
        title=('恢复工作：' if recover_latest else '打开项目：')+Path(path).name
        self.last_error='';self.progress_presentation.begin_loading('project_recovery' if recover_latest else 'project_open',title);self.update_controls()
        def finish_status(outcome):
            nonlocal settled
            if settled:return
            settled=True;self.progress_presentation.finish_loading(outcome);self.update_controls()
        def done(loaded):
            nonlocal committed
            if self.closing or task.cancel_event.is_set():
                finish_status('cancelled');self.finish_project_transition(False);return
            committed=bool(self.open_project(path,recover_latest,_loaded=loaded))
            finish_status('complete' if committed else 'failed')
            self.finish_project_transition(committed)
        def failed(message):
            if self.closing or task.cancel_event.is_set():
                finish_status('cancelled');self.finish_project_transition(False);return
            finish_status('failed')
            self.finish_project_transition(False);self.error(message)
        def finished():
            self.loading_task=None
            if not settled:
                finish_status('cancelled' if task.cancel_event.is_set() else 'failed');self.finish_project_transition(False)
            if self.closing:QTimer.singleShot(0,self.close)
            else:
                self.update_controls();QTimer.singleShot(0,self.pump_preparation)
        transition=self.project_transition
        def progress(current,total,text):
            if settled or task.cancel_event.is_set() or self.closing or self.project_transition is not transition:return
            transition.set_stage(text);self.progress_presentation.update_loading(current,total,text)
        def resolve(payload):
            project,event,answer=payload
            try:
                if not self.closing and not task.cancel_event.is_set():answer['changed']=self.resolve_missing_project_sources(project)
            finally:event.set()
        task.signals.progress.connect(progress)
        task.signals.preview.connect(resolve)
        task.signals.result.connect(done);task.signals.error.connect(failed);task.signals.finished.connect(finished)
        self.load_pool.start(task);return True

    def finish_project_transition(self,committed):
        transition=self.project_transition
        if transition is None:return
        def complete():
            if self.project_transition is transition:self.project_transition=None
            if not self.closing:self.update_controls()
            if committed and not self.closing:self.complete_project_open()
        transition.finish(complete,animate=committed and self.isVisible() and not self.closing)

    def commit_project(self,loaded,path):
        if getattr(loaded,'cache_cleared',False) or self.service.cache_generation!=getattr(self,'cache_generation',0):
            for image in loaded.project['images']:
                image['ready']=False;image.pop('prepared_full_signature',None)
                if image.get('preparation_state')=='ready':image.pop('preparation_state')
            self.runtime_status=None;self.model_warmup_signature=None
        for image in loaded.project['images']:
            if image.get('ready') and image.get('prepared_cache_revision')!=self.service.cache_revision:
                image['ready']=False;image.pop('prepared_full_signature',None)
                image.pop('preparation_state',None)
        self.cache_generation=self.service.cache_generation
        self.restoring_project=True;self.auto_apply_timer.stop();self.render_timer.stop();self.smoother.clear()
        self.prompt_revision+=1;epoch=self.project_epoch+1
        runtime=self.runtime_status if (self.runtime_status or {}).get('signature')==digest(loaded.project['model']) else None
        try:
            with blocked_controls(self):
                self.preparation.reset();self.image_sessions.clear()
                self.state=WorkbenchState(loaded.project,project_path=Path(path),image=loaded.image,draft=loaded.draft,mode_index=loaded.mode_index,project_epoch=epoch)
                self.runtime_status=runtime
                self.label_lookup.clear();self.label_indexes.clear();self.label_index_key=None;self.label_index=None
                self.render_generation+=1;self.raster_renderer.reset(self.render_generation,clear_cache=True)
                from ..resource_location import current_resource_dir
                roots=[data_dir()]
                try:roots.append(current_resource_dir())
                except (OSError,ValueError):pass
                from ..project_files import RECOVERY_NAME
                untitled=[root/'recovery'/RECOVERY_NAME for root in roots]
                if Path(path).resolve() in {base.resolve() for base in untitled}:self.project_path=None
                state=self.project.get('workspace',{})
                self.tool_modes=dict(state.get('tools',{}))
                self.auto_apply.setChecked(state.get('auto_apply',True));self.single_polygon.setChecked(state.get('single_polygon',False))
                raw_view=state.get('raw_view',False);self.raw_view_action.setChecked(True);self.refresh_classes()
                session={}
                if self.image:
                    session=self.load_image_session();self.draft=loaded.draft
                changed_images={image['id'] for image in self.project['images'] if image.pop('_relinked',False)}
                if changed_images:self.invalidate_model_drafts(changed_images)
                chosen=state.get('class_id') or session.get('class_id') or self.draft.get('class_id')
                if chosen is not None:self.classes.setCurrentIndex(self.classes.findData(chosen))
                self.restore_label_histories();self.refresh_images();self.refresh_info();self.refresh_project_title()
                self.refresh_export_crs(force=True)
                self.refresh_export_label_field(force=True)
                self.view.set_image(self.image['width'],self.image['height']) if self.image else self.view.set_image(0,0)
                if loaded.draft_path is not None:self.view.path_cache[id(self.draft['geometry'])]=(self.draft['geometry'],loaded.draft_path)
                if self.image:
                    if loaded.navigation:self.view.restore_navigation(loaded.navigation)
                    elif loaded.view_window:self.view.fitInView(QRectF(*loaded.view_window),Qt.AspectRatioMode.KeepAspectRatio)
                    self.view.update_scrollbar_visibility()
                self.view.set_overlay_visibility(True)
                self.label_index=loaded.index;self.label_index_key=self.label_index_signature()
                self.label_indexes[self.annotation_context()]=(self.label_index_key,self.label_index)
                if loaded.frame is not None:
                    full=[0,0,self.image['width'],self.image['height']]
                    if loaded.overview is not None:
                        self.raster_renderer.prime(self.image,full,min(loaded.size,1600),loaded.overview)
                        self.view.show_raster(*loaded.overview,full,overview=True)
                    self.raster_renderer.prime(self.image,loaded.window,loaded.size,loaded.frame)
                    self.view.show_raster(*loaded.frame,loaded.window,overview=loaded.window==full)
                    self.view.layers.raster_epoch=self.render_generation
                elif self.image:
                    self.view.loading.setText(ui_text('project.display_bands'));self.view.loading.adjustSize()
                if loaded.smoothing:
                    sources,value=loaded.smoothing;self.smoother.prime(self.smoothing_key(sources),sources,value)
                self.refresh_labels();self.update_draft_info();self.update_controls()
                tool=state.get('tool',self.tool_modes.get(self.annotation_mode()))
                self.restore_tool(tool)
                manual=state.get('reshape')
                if manual and self.image:
                    if manual.get('target') not in ('draft','auto'):self.selected_id=manual['label_id'];self.selected_ids={self.selected_id}
                    self.begin_reshape(auto=manual.get('target')=='auto')
                    if self.reshape_session is not None:
                        self.reshape_session['stroke']=copy.deepcopy(manual.get('stroke',[]));self.reshape_session['alternate']=bool(manual.get('alternate'))
                        self.reshape_session['redo_stroke']=copy.deepcopy(manual.get('redo_stroke',[]))
                        self.view.set_reshape_stroke(self.reshape_session['stroke'])
                        if tool=='pan':self.restore_tool('pan')
                        self.update_controls()
                self.raw_view_action.setChecked(not raw_view);self.view.set_overlay_visibility(not raw_view);self.update_controls()
                self.settings.setValue('last_project',str(path));self.settings.setValue('recovery/last_work',str(path))
                self.log_message(ui_text('projects.open_project.005'));self.dirty=False
                if getattr(loaded,'reconciled_caches',0) or getattr(loaded,'sources_changed',False):self.mark_dirty()
                self.raster_list_sizer.settle()
                self.render_timer.stop();self.auto_apply_timer.stop()
        finally:self.restoring_project=False
        if self.dirty:self.autosave_debounce.start()
        if self.project_transition is None:self.complete_project_open()
        return True

    def complete_project_open(self):
        self.view.setFocus();state=self.project.get('workspace',{})
        if self.image and self.view.layers.detail_item is not None and self.view.layers.base_item is None:self.request_render(True)
        self.queue_preparation(resume=not state.get('preparation_paused',False))
