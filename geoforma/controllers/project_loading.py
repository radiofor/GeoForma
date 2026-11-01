"""Background project staging and a single signal-blocked workbench commit."""
import copy,traceback
from contextlib import contextmanager
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,QSignalBlocker,QRectF
from PySide6.QtWidgets import QMessageBox
from ..tasks import Task
from ..domain import data_dir
from ..domain import digest
from ..workbench_state import WorkbenchState
from ..project_loading import prepare_project
from ..ui.text import ui_text


@contextmanager
def blocked_controls(window):
    names=('images','classes','auto_apply','single_polygon','label_filter',
           'smooth_enabled','smooth_value','raw_view_action','view')
    blockers=[QSignalBlocker(getattr(window,name)) for name in names]
    updates=window.updatesEnabled();window.setUpdatesEnabled(False)
    try:yield
    finally:
        for blocker in reversed(blockers):blocker.unblock()
        window.setUpdatesEnabled(updates)


class ProjectLoadingWorkflow:
    def project_source(self,path,recover_latest=False):
        actual=Path(path);recovery=Path(str(path)+'.autosave')
        if recovery.exists() and (not actual.exists() or recovery.stat().st_mtime_ns>actual.stat().st_mtime_ns):
            if recover_latest or QMessageBox.question(self,ui_text('projects.open_project.010'),ui_text('projects.open_project.011'))==QMessageBox.StandardButton.Yes:actual=recovery
        return actual

    def request_project_open(self,path,recover_latest=False):
        if self.task or self.reshape_session is not None or self.loading_task or self.project_transition or self.closing:return False
        from ..resource_migration import pending_migration
        try:pending=bool(pending_migration())
        except (OSError,ValueError,RuntimeError):pending=True
        if pending:
            self.statusBar().showMessage('请先完成资源迁移，再打开项目。',6000);return False
        try:
            if self.autosave() is False:return False
            actual=self.project_source(path,recover_latest)
        except Exception:self.error(traceback.format_exc());return False
        self.auto_apply_timer.stop();self.render_timer.stop()
        if self.candidate_task:self.candidate_task.cancel()
        from ..ui.project_transition import ProjectTransition
        self.project_transition=ProjectTransition(self,recover_latest)
        size=(self.view.viewport().width(),self.view.viewport().height())
        def work(task):
            from ..resource_location import require_resource_dir
            self.wait_for_project_saves(task)
            root=require_resource_dir()
            loaded=prepare_project(actual,size,task)
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
        task.signals.progress.connect(progress)
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
                self.label_lookup.clear();self.candidate_indexes.clear();self.candidate_key=None;self.candidate_index=None
                self.render_generation+=1;self.raster_renderer.reset(self.render_generation,clear_cache=True)
                from ..resource_location import current_resource_dir
                roots=[data_dir()]
                try:roots.append(current_resource_dir())
                except (OSError,ValueError):pass
                untitled=[root/'recovery'/'untitled.geoforma.json' for root in roots]
                if Path(path).resolve() in {candidate.resolve() for base in untitled for candidate in (base,Path(str(base)+'.autosave'),Path(str(base)+'.bak'))}:self.project_path=None
                state=self.project.get('workspace',{})
                self.tool_modes=dict(state.get('tools',{}))
                self.label_filter.setCurrentIndex(0)
                self.auto_apply.setChecked(state.get('auto_apply',True));self.single_polygon.setChecked(state.get('single_polygon',False))
                raw_view=state.get('raw_view',False);self.raw_view_action.setChecked(True);self.refresh_classes()
                session={}
                if self.image:
                    session=self.load_image_session();self.draft=loaded.draft
                if getattr(loaded,'nodata_model_changed',()):self.invalidate_model_drafts(set(loaded.nodata_model_changed))
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
                self.candidate_index=loaded.index;self.candidate_key=self.candidate_signature()
                self.candidate_indexes[self.annotation_context()]=(self.candidate_key,self.candidate_index)
                if loaded.frame is not None:
                    full=[0,0,self.image['width'],self.image['height']]
                    if loaded.overview is not None:self.view.show_raster(*loaded.overview,full,overview=True)
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
                if getattr(loaded,'reconciled_caches',0) or getattr(loaded,'nodata_migration_changed',False):self.mark_dirty()
                self.raster_list_sizer.settle()
                self.render_timer.stop();self.auto_apply_timer.stop()
        finally:self.restoring_project=False
        if self.project_transition is None:self.complete_project_open()
        return True

    def complete_project_open(self):
        self.view.setFocus();state=self.project.get('workspace',{})
        if self.image and self.view.layers.detail_item is not None and self.view.layers.base_item is None:self.request_render(True)
        self.queue_preparation(resume=not state.get('preparation_paused',False))
