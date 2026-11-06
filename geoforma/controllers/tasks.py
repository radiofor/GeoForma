"""TaskWorkflow responsibilities in the Qt application layer."""
from __future__ import annotations
from ..ui.text import ui_text
import traceback
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox
from ..tasks import Task
from ..theme import set_tone
from ..domain import digest
from ..task_status import visible_detail
from ..ui.modal import dialog_result


class TaskWorkflow:
    def log_message(self,text):self.log.appendPlainText(datetime.now().strftime('%H:%M:%S')+'  '+str(text))

    def error(self,text):
        from ..error_messages import user_message
        self.last_error='' if ui_text('tasks.error.004') in text else user_message(text)
        self.log_message(text);self.task_text.setText(self.last_error)
        self.state_label.setText(ui_text('tasks.error.003'))
        set_tone(self.state_label,'error')
        if ui_text('tasks.error.004') not in text:
            from ..error_messages import user_message
            retry=getattr(self.task,'retry_operation',None)
            buttons=QMessageBox.StandardButton.Ok
            if retry:buttons|=QMessageBox.StandardButton.Retry
            box=QMessageBox(QMessageBox.Icon.Warning,ui_text('errors.title'),user_message(text),buttons,self)
            box.setDetailedText(text)
            if retry:box.button(QMessageBox.StandardButton.Retry).setText('重试')
            _,retry_requested=dialog_result(box,lambda dialog:dialog.clickedButton()==dialog.button(QMessageBox.StandardButton.Retry) and retry,owner=self)
            # The dialog has its own event loop; finished may already have run.
            if retry_requested:
                if self.task is not None:self.pending_task_retry=retry
                else:QTimer.singleShot(0,self,retry)

    def run(self,title,fn,callback,kind=None,on_error=None,on_finished=None,deferred_valid=None):
        from ..operation_state import can_start_operation
        def resume():
            if deferred_valid is not None and not deferred_valid():return
            self.run(title,fn,callback,kind,on_error,on_finished,deferred_valid)
        if kind in ('interactive','reshape','manual_polygon','history','export') and self.defer_for_prefetch(resume):return True
        if not can_start_operation(self):return False
        retry_title=title;retry_fn=fn;context=self.annotation_context()
        retry_model=(self.project_epoch,digest(self.project['model']))
        if kind in ('model','model_warmup','preparation','interactive') and not self.ensure_model_resources():return False
        self.invalidate_preview()
        if kind in ('cache_cleanup','import','reference_import','model','model_warmup','preparation','interactive'):
            from ..resource_location import require_resource_dir
            owner=self.project['cache_id'];operation=fn
            def fn(task):
                root=require_resource_dir()
                self.service.activate_project(root,owner)
                return operation(task)
        self.last_error='';self.pending_task_retry=None;task=Task(fn);self.task=task;self.task_kind=kind
        def retry():
            if self.closing:return False
            if kind in ('model','model_warmup'):
                if retry_model!=(self.project_epoch,digest(self.project['model'])):return False
            elif context!=self.annotation_context():return False
            if kind=='preparation' and self.image:
                target=next((im for im in self.project['images'] if im['id']==retry_image_id),None)
                if target is None:return False
                self.preparation.paused=False;self.start_preparation(target);return True
            return self.run(retry_title,retry_fn,callback,kind,on_error,on_finished)
        retry_image_id=self.preparing_id
        task.retry_operation=retry if kind in ('model','model_warmup','preparation') else None
        if kind in ('model','model_warmup','preparation'):self.model_warmup_signature=retry_model[1]
        if kind in ('model','model_warmup'):
            from ..model_catalog import model_title
            title='加载模型：'+model_title(self.project['model'])
        elif kind in ('interactive','reshape','manual_polygon','bands','export','history') and self.image:
            name=self.image.get('name') or Path(self.image.get('path','')).name or self.image.get('id','当前影像')
            title=title.rstrip('…')+'：'+name
        self.task_title=title;self.task_stage='';self.task_outcome='running';self.progress_presentation.begin()
        revision=self.prompt_revision
        if kind=='interactive':
            def preview(value):
                if self.task is task and not task.cancel_event.is_set() and revision==self.prompt_revision and context==self.annotation_context() and not self.closing and self.raw_view_action.isChecked():
                    bitmap=value['mask']
                    if self.mode_index==0 and self.single_polygon.isChecked() and not value.get('single_polygon'):
                        from ..single_polygon import single_preview
                        bitmap=single_preview(bitmap,value['window'],self.draft.get('points',[]))
                    self.view.show_preview(bitmap,value['window'],value.get('box',self.draft.get('box')))
            task.signals.preview.connect(preview)
        def done(value):
            if self.task is not task:return
            if task.cancel_event.is_set() or self.closing:
                self.task_outcome='cancelled';return
            if self.service.cache_generation!=getattr(self,'cache_generation',0) or kind=='cache_cleanup' and self.service.cache_changed:
                self.cache_generation=self.service.cache_generation
                self.runtime_status=None;self.model_warmup_signature=None
                for image in self.project['images']:
                    image['ready']=False;image.pop('prepared_full_signature',None)
                    if image.get('preparation_state')=='ready':image.pop('preparation_state')
                if self.auto_prepare:self.queue_preparation(resume=not self.preparation.paused)
            try:callback(value)
            except Exception:self.task_outcome='failed';self.error(traceback.format_exc())
        def failed(message):
            if self.task is not task:return
            self.task_outcome='cancelled' if task.cancel_event.is_set() or ui_text('tasks.error.004') in message else 'failed'
            if kind=='interactive':self.view.clear_preview()
            if on_error:on_error(message)
            if self.task_outcome=='cancelled':
                if getattr(task,'preparation_superseded',False):return
                self.last_error=ui_text('resources.stopped_hint') if kind=='resource_install' else '已准备的缓存保留' if kind=='preparation' else ''
                self.log_message(message);return
            if kind=='resource_install':
                from ..error_messages import user_message
                self.last_error=user_message(message);self.log_message(message);return
            if kind=='reshape':
                self.log_message(message);return
            self.error(message)
        progress=lambda current,total,text:self.task_progress(current,total,text) if self.task is task else None
        finished=lambda:self.finished(on_finished) if self.task is task else None
        if kind in ('import','reference_import'):
            from ..ui.ordered_progress import OrderedProgressDelivery
            delivery=OrderedProgressDelivery(self,task,progress,done,failed,finished)
            task.signals.progress.connect(delivery.progress);task.signals.result.connect(delivery.result)
            task.signals.error.connect(delivery.error);task.signals.finished.connect(delivery.finished)
        else:
            task.signals.progress.connect(progress);task.signals.result.connect(done)
            task.signals.error.connect(failed);task.signals.finished.connect(finished)
        self.progress_image_order=next(((i+1,len(self.project['images'])) for i,image in enumerate(self.project['images']) if kind=='preparation' and image['id']==self.preparing_id),None)
        self.update_progress_count(0,0)
        self.task_text.setText(visible_detail(title,kind=kind));self.log_message(title);self.update_controls();self.pool.start(task);return True

    def update_progress_count(self,current,total):
        order=getattr(self,'progress_image_order',None)
        stage=getattr(self,'task_stage','')
        value=max(0,min(current,total)) if total>0 else 0
        unit=None
        if self.task_kind=='preparation' and stage.startswith(('准备影像','检查完整影像缓存')):unit='块'
        elif self.task_kind in ('import','reference_import'):unit={'import':'影像','reference_import':'参考'}[self.task_kind]
        elif self.task_kind=='export' and stage.startswith('导出 ') and not stage.startswith('导出原始网格'):unit='标签'
        count=(f'{unit} {value} / {total}' if unit else f'{100*value//total}%') if total>0 else ''
        if order:
            prefix=f'影像 {order[0]}/{order[1]}'
            count=prefix if total<=0 else prefix+' · '+count
        self.progress_count.setText(count)
        self.progress_count.setVisible(bool(total>0 or order))

    def task_progress(self,current,total,text):
        cancelled=getattr(self.task,'cancel_event',None)
        if cancelled and cancelled.is_set():return
        self.task_stage=text
        self.progress_presentation.report(current,total,text)
        if self.task:self.progress_presentation.sync(True)
        if self.task_kind=='preparation':
            from ..model_catalog import model_title
            model=model_title(self.project['model'])
        else:model=None
        self.task_text.setText(visible_detail(getattr(self,'task_title',''),text,self.task_kind,model=model))
        self.update_progress_count(current,total)
        if self.task_kind=='preparation' and self.preparing_id:
            image=next((im for im in self.project['images'] if im['id']==self.preparing_id),None)
            if image and total and text.startswith(('准备影像','检查完整影像缓存')):image['preparation_progress']=[current,total];self.mark_dirty(background=True)

    def finished(self,on_finished=None):
        title=self.task_title
        kind=self.task_kind
        superseded=getattr(self.task,'preparation_superseded',False)
        outcome=self.task_outcome
        if outcome=='running':outcome='cancelled' if self.task.cancel_event.is_set() else 'complete'
        if kind in ('model','model_warmup','preparation','interactive') and outcome in ('failed','cancelled') and not self.service.ready:
            # A terminated worker no longer owns the device shown by the UI.
            # Image features remain valid and must not be marked unprepared.
            self.runtime_status=None
        if kind=='preparation' and outcome=='cancelled':
            target=next((im for im in self.project['images'] if im['id']==self.preparing_id),None)
            # A backend may return just after cancellation without raising.
            # Never leave its row stuck in the active preparation state.
            if target and target.get('preparation_state')=='preparing':
                target['preparation_state']=('queued' if target['id'] in self.preparation.ids else 'pending') if superseded else 'paused'
                if not superseded:self.preparation.add([target['id']])
                self.refresh_images();self.mark_dirty(background=True)
        self.task.retry_operation=None
        self.task=None;self.preparing_id=None
        if self.last_error and outcome=='complete':outcome='failed'
        self.progress_presentation.finish(title,outcome)
        self.task_kind=None;self.task_title='';self.task_stage='';self.progress_image_order=None
        self.progress_presentation.restore_text()
        if on_finished:
            try:on_finished()
            except Exception:
                message=traceback.format_exc()
                if self.task is None:
                    self.error(message);self.progress_presentation.finish(title,'failed')
                else:self.log_message(message)
        # A completion hook may start another task. Its state now owns the UI.
        if self.task is not None:return
        pending=self.pending_prefetch_work;self.pending_prefetch_work=None
        if pending and not self.closing and pending[0]==self.annotation_context():
            pending[1]()
            if self.task is not None:return
        retry=getattr(self,'pending_task_retry',None);self.pending_task_retry=None
        if retry and not self.closing:
            QTimer.singleShot(0,self,retry);self.update_controls();return
        # Hand the queue directly to the next image before exposing idle controls.
        # Cached images can finish quickly; an idle/active pulse per file makes
        # both sidebars, feedback overlays and the list flash repeatedly.
        if kind=='preparation' and (outcome=='complete' or superseded) and self.auto_prepare and not self.closing and not self.preparation.paused:
            self.pump_preparation()
            if self.task is not None:return
        self.update_controls();self.autosave()
        if not self.last_error and self.auto_apply.isChecked() and self.draft.get('pending'):self.auto_apply_timer.start()
        if self.closing:QTimer.singleShot(0,self.close)
        else:
            QTimer.singleShot(0,self.pump_preparation)

    def cancel(self):
        self.pending_prefetch_work=None;self.auto_apply_timer.stop()
        if self.task:
            text=ui_text('tasks.cancel.010') if self.task_kind=='preparation' else ui_text('tasks.cancel.011')
            if not self.progress_presentation.request_cancel(text):return
            if self.task_kind=='preparation':self.preparation.paused=True
            self.task.cancel();self.task_text.setText(visible_detail(self.task_title,text,self.task_kind));self.update_controls()
        elif self.loading_task:
            self.loading_task.cancel()
            self.progress_presentation.request_cancel('正在停止加载…')
            if not self.closing:self.update_controls()

