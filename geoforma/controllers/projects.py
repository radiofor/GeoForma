"""ProjectWorkflow responsibilities in the Qt application layer."""
from __future__ import annotations
from ..ui.text import ui_text
import copy, traceback, time
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QMessageBox
from ..domain import new_project, data_dir
from ..storage import save_project, project_snapshot
from ..tasks import Task
from ..model_preferences import last_model
from ..operation_state import interaction_locked,can_start_operation
from ..project_files import PROJECT_SUFFIX,RECOVERY_NAME,SAVE_FILTER,OPEN_FILTER,new_project_path,project_name


class ProjectWorkflow:
    def previous_work(self):
        from ..recovery import recovery_target
        from ..resource_location import current_resource_dir
        try:root=current_resource_dir()
        except (OSError,ValueError):root=data_dir()
        return recovery_target(self.settings,root,data_dir())

    def recover_previous_work(self):
        if not can_start_operation(self) or self.autosave_task or self.project_path or self.project['images'] or self.project['labels'] or self.project.get('references'):return
        path=self.previous_work()
        if path:self.request_project_open(path,recover_latest=True)
        else:self.statusBar().showMessage(ui_text('project.no_recovery'),3000);self.update_controls()

    def mark_dirty(self):
        self.dirty=True;self.dirty_revision+=1
        timer=getattr(self,'autosave_debounce',None)
        if timer is not None and not self.closing and not self.restoring_project:timer.start()

    def refresh_project_title(self):
        path=self.project_path
        name=project_name(path) if path else ui_text('projects.new.001')
        self.project_title.setText(name);self.project_title.setToolTip(str(path.resolve()) if path else '')
        self.project_directory_button.setEnabled(bool(path))

    def open_project_directory(self):
        if not self.project_path:return
        directory=self.project_path.parent
        if not directory.is_dir():
            QMessageBox.warning(self,'项目目录不可用','项目所在文件夹不存在或不可访问。若项目已移动，请从新位置重新打开项目。')
        elif not QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory.resolve()))):
            QMessageBox.warning(self,'无法打开项目目录','无法打开项目所在文件夹，请检查系统文件管理器设置。')

    def capture_workspace(self):
        draft={k:copy.deepcopy(v) for k,v in self.draft.items() if k not in ('logits','choices')}
        self.project['workspace']={'image_id':self.image['id'] if self.image else None,'draft':draft,'class_id':self.classes.currentData(),
            'view_window':self.view.visible_window() if self.image else None,'operation':0,'preparation_paused':self.preparation.paused}
        self.project['workspace']['annotation_mode']=self.annotation_mode();self.project['workspace']['auto_apply']=self.auto_apply.isChecked()
        self.project['workspace']['single_polygon']=self.single_polygon.isChecked()
        self.project['workspace']['navigation']=self.view.capture_navigation() if self.image else None
        self.project['workspace']['raw_view']=not self.raw_view_action.isChecked()
        self.tool_modes[self.annotation_mode()]=self.view.selected_mode
        self.project['workspace']['tool']=self.view.selected_mode
        self.project['workspace']['tools']=dict(self.tool_modes)
        if self.reshape_session is not None:
            self.project['workspace']['reshape']={'label_id':self.reshape_session['label']['id'],
                'target':self.reshape_session.get('target','label'),'stroke':copy.deepcopy(self.reshape_session['stroke']),'redo_stroke':copy.deepcopy(self.reshape_session.get('redo_stroke',[])),'alternate':self.reshape_session['alternate']}
        self.store_image_session()
        self.capture_label_histories()

    def autosave(self):
        timer=getattr(self,'autosave_debounce',None)
        if timer is not None:timer.stop()
        if not self.dirty and not self.project_saves.failed and not self.project_saves.pending:return
        from ..resource_migration import pending_migration
        try:pending=bool(pending_migration())
        except (OSError,ValueError,RuntimeError):pending=True
        if pending or getattr(getattr(self,'resource_dialog',None),'migration_active',False):
            self.log_message('资源迁移未完成，自动保存暂不可用。请先继续迁移。')
            if self.closing:
                self.abort_shutdown();QMessageBox.warning(self,'自动保存未完成','请先完成资源迁移，再关闭 GeoForma。')
            return False
        # Opening and closing a blank workspace must preserve previous work.
        self.project_saves.retry_failed()
        if self.dirty and (self.project_path or self.project['images'] or self.project.get('references')):
            from ..resource_location import current_resource_dir
            from ..project_save_queue import ProjectSaveRequest
            self.capture_workspace()
            try:path=self.project_path if self.project_path else current_resource_dir()/'recovery'/RECOVERY_NAME
            except (OSError,ValueError,RuntimeError):path=None
            if path is None:
                self.log_message(ui_text('projects.autosave_unavailable'))
                if self.closing:
                    self.abort_shutdown();QMessageBox.warning(self,ui_text('projects.failed.007'),ui_text('projects.failed.008'))
                return False
            request=ProjectSaveRequest(project_snapshot(self.project),path,self.project_path,self.project_epoch,self.dirty_revision,self.project_title.text(),self.project_saves.next_order())
            # Capture before returning even while another project is writing.
            # Switching projects must not discard its latest pending edits.
            self.project_saves.submit(request)
        self.start_next_autosave()
        return True

    def wait_for_project_saves(self,task):
        """Background loading waits for accepted snapshots before reading files."""
        while self.project_saves.busy:
            task.check();time.sleep(.005)
        task.check()
        if self.project_saves.failed:raise RuntimeError(ui_text('projects.save_pending'))

    def start_next_autosave(self):
        if self.autosave_task:return
        request=self.project_saves.pop()
        if request is None:return
        from ..resource_location import require_resource_dir
        path=request.path;original_path=request.project_path
        def save_snapshot(t):
            if original_path is None and require_resource_dir()!=path.parent.parent:raise RuntimeError('资源目录已更改，自动保存已取消。')
            if original_path is not None:
                if not original_path.is_file():raise RuntimeError('项目文件不存在或已移动，自动保存已暂停；请先将项目文件移回原位置。')
                save_project(request.snapshot,original_path)
            else:save_project(request.snapshot,path)
        task=Task(save_snapshot);self.autosave_task=task
        self.background_activity.set('autosave','自动保存',request.title,task)
        def saved(_):
            self.project_saves.saved(request.destination,request.order)
            if request.epoch==self.project_epoch and self.project_path==original_path:
                self.settings.setValue('recovery/last_work',str(original_path or path))
                if request.revision==self.dirty_revision:
                    self.dirty=False;self.statusBar().showMessage(ui_text('projects.saved.003' if original_path else 'projects.recovery_saved'),2000)
                self.update_controls()
        def finished():
            self.autosave_task=None
            self.project_saves.complete()
            self.background_activity.set('autosave','')
            if not self.closing:self.update_controls()
            if self.project_saves.pending:QTimer.singleShot(0,self.start_next_autosave)
            elif self.closing:QTimer.singleShot(0,self.close)
        def failed(message):
            if self.project_saves.stale(request):return
            self.project_saves.defer(request)
            self.log_message(ui_text('projects.failed.006')+message)
            self.statusBar().showMessage(ui_text('projects.autosave_error'),10000)
            if self.closing:
                self.abort_shutdown()
                QMessageBox.warning(self,ui_text('projects.failed.007'),ui_text('projects.failed.008'))
        task.signals.result.connect(saved);task.signals.error.connect(failed);task.signals.finished.connect(finished);self.storage_pool.start(task)

    def save(self):
        if interaction_locked(self):return
        path=self.project_path
        first_save=path is None
        if not path:
            value,_=QFileDialog.getSaveFileName(self,ui_text('projects.save.004'),str(Path.cwd()/('project'+PROJECT_SUFFIX)),SAVE_FILTER)
            if not value:return
            path=new_project_path(value)
            if path!=Path(value) and path.exists():
                if QMessageBox.question(self,'替换文件',f'文件已存在，是否替换？\n{path}',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
        self.capture_workspace();self.project['name']=project_name(path)
        snapshot=project_snapshot(self.project)
        order=self.project_saves.next_order()
        try:
            # The visible action is used only for the first save. Keep this
            # synchronous API safe for existing automation as well.
            self.storage_pool.waitForDone()
            save_project(snapshot,path);self.project_saves.saved(path,order)
            if first_save:
                # The saved snapshot supersedes queued recovery writes for this
                # workspace; no later edit can occur while this method blocks.
                for queue in (self.project_saves.pending,self.project_saves.failed):
                    for key,request in list(queue.items()):
                        if request.epoch==self.project_epoch and request.project_path is None:queue.pop(key,None)
                try:
                    from ..recovery import discard_saved_untitled
                    from ..resource_location import current_resource_dir
                    discard_saved_untitled(current_resource_dir(),self.project.get('cache_id'))
                except (OSError,ValueError,RuntimeError):
                    self.log_message('项目已保存，但未能清理未命名项目的恢复记录。')
            self.project_path=path;self.dirty=False;self.refresh_project_title();self.log_message(ui_text('projects.save.009')+str(path));self.settings.setValue('last_project',str(path));self.settings.setValue('recovery/last_work',str(path));self.update_controls()
        except Exception:self.error(traceback.format_exc())

    def new(self):
        if not can_start_operation(self) or self.reshape_session is not None:return
        self.remember_current_model()
        if self.label_index_task:self.label_index_task.cancel()
        if self.autosave() is False:return
        self.smoother.clear();self.project_epoch+=1;self.preparation.reset();self.image_sessions.clear();self.project=new_project(last_model(self.settings));self.project_path=None;self.image=None;self.draft={};self.label_undo=[];self.label_redo=[];self.prompt_undo=[];self.prompt_redo=[];self.selected_id=None;self.selected_ids.clear();self.selected_points.clear();self.render_generation+=1;self.raster_renderer.reset(self.render_generation,clear_cache=True);self.view.set_image(0,0);self.refresh_classes();self.refresh_images();self.refresh_labels();self.update_draft_info();self.update_controls();self.refresh_project_title();self.dirty=False
        self.mode_histories.clear();self.auto_apply.setChecked(True)
        self.single_polygon.setChecked(self.project['workspace']['single_polygon'])
        self.label_lookup.clear();self.label_indexes.clear();self.label_index_key=None;self.label_index=None
        self.clear_project_cache()

    def clear_project_cache(self,callback=None):
        """Asynchronous ownership switch; source imagery and saved work are untouched."""
        self.run('清理旧项目的影像缓存',lambda task:None,callback or (lambda _:None),kind='cache_cleanup')

    def open_dialog(self):
        if not can_start_operation(self):return
        path,_=QFileDialog.getOpenFileName(self,ui_text('projects.open_dialog.002'),str(self.project_path or Path.cwd()),OPEN_FILTER)
        if path:self.request_project_open(path)

    def open_project(self,path,recover_latest=False,_loaded=None):
        """Synchronous API; UI entry points prepare in the background before committing."""
        if self.task or self.reshape_session is not None or self.closing:return False
        from ..resource_migration import pending_migration
        try:pending=bool(pending_migration())
        except (OSError,ValueError,RuntimeError):pending=True
        if pending:
            self.statusBar().showMessage('请先完成资源迁移，再打开项目。',6000);return False
        if _loaded is None and not can_start_operation(self):return False
        try:
            from ..project_loading import prepare_project
            if _loaded is None:
                if self.autosave() is False:return False
                if self.project_path and Path(path)==self.project_path and self.autosave_task:self.save()
                actual=Path(path)
                from ..storage import load_project
                from ..missing_sources import missing_sources
                project=load_project(actual);changed=False
                if missing_sources(project):
                    changed=self.resolve_missing_project_sources(project)
                    if changed is None:return False
                if changed:
                    from ..missing_sources import validate_resolved_project
                    validate_resolved_project(project)
                _loaded=prepare_project(actual,(self.view.viewport().width(),self.view.viewport().height()),project=project)
                _loaded.sources_changed=changed
            from ..resource_location import require_resource_dir
            cache_root=require_resource_dir()
            if not hasattr(_loaded,'cache_cleared'):_loaded.cache_cleared=self.service.activate_project(cache_root,_loaded.project['cache_id'])
            if not _loaded.cache_cleared and not hasattr(_loaded,'reconciled_caches'):
                from ..cache_recovery import reconcile_prepared
                _loaded.reconciled_caches=reconcile_prepared(_loaded.project,cache_root,self.service.cache_revision)
            return self.commit_project(_loaded,path)
        except Exception:
            self.restoring_project=False;self.error(traceback.format_exc());return False
