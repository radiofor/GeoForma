"""Current/next image preparation policy, separate from generic task execution."""
import copy
from PySide6.QtCore import QTimer
from ..domain import digest
from ..raster_snapshot import image_snapshot
from ..workflow import full_bounds,preparation_signature,fully_prepared,preparation_window
from ..ui.text import ui_text


class PreparationWorkflow:
    def foreground_task_active(self):
        from ..operation_state import background_prefetch
        return bool(self.task and not background_prefetch(self))

    def defer_for_prefetch(self,callback,allow_prompt_changes=False):
        from ..operation_state import background_prefetch
        if not background_prefetch(self):return False
        context=self.annotation_context();self.pending_prefetch_work=(context,callback,allow_prompt_changes)
        self.task.preparation_superseded=True
        self.preparation.add([self.preparing_id]);self.task.cancel()
        if not allow_prompt_changes:self.update_controls()
        return True

    def queue_preparation(self,resume=True):
        if not self.auto_prepare:return
        targets=preparation_window(self.project['images'],self.image)
        wanted={image['id'] for image in targets}
        if self.task_kind=='preparation' and self.task is not None and self.preparing_id not in wanted:
            # Keep completed cache blocks when an obsolete prefetch is stopped.
            self.task.preparation_superseded=True;self.task.cancel()
        active=self.preparing_id if self.task_kind=='preparation' and self.task is not None and not self.task.cancel_event.is_set() else None
        for image in self.project['images']:
            if image['id'] not in wanted and image.get('preparation_state') in ('queued','paused'):
                image.pop('preparation_state',None)
        for image in targets:
            if not fully_prepared(image,self.project['model']):
                image['ready']=False
                image['preparation_state']=('preparing' if image['id']==active else 'queued' if resume else 'paused') if image.get('model_recipe') else 'bands_required'
        self.preparation.replace(im['id'] for im in targets if im['id']!=active and not fully_prepared(im,self.project['model']))
        self.preparation.paused=not resume
        self.refresh_images();QTimer.singleShot(0,self.pump_preparation)

    def pump_preparation(self):
        if self.task or self.loading_task or self.project_transition or self.closing or self.restoring_project or not self.auto_prepare:return
        if not self.project['images'] and self.image is None:return
        if not self.ensure_model_resources():return
        target=self.preparation.next(self.project)
        if target is None:
            if self.image and self.image.get('ready'):
                config=copy.deepcopy(self.project['model']);signature=digest(config)
                # A completed image cache still needs a resident model.
                if signature!=(self.runtime_status or {}).get('signature') and signature!=self.model_warmup_signature:
                    def ready(result):
                        self.project['model']['checkpoint']=result['checkpoint'];self.record_runtime(result);self.mark_dirty(background=True)
                    self.run(ui_text('tasks.warmup_model'),lambda t:self.service.prepare_model(config,t),ready,kind='model_warmup')
                    return
            self.update_controls();return
        self.start_preparation(target)

    def start_preparation(self,target):
        if not self.ensure_model_resources():return
        image=image_snapshot(target);config=copy.deepcopy(self.project['model']);bounds=full_bounds(target)
        target['ready']=False;target['preparation_state']='preparing';self.preparing_id=target['id'];self.refresh_images()
        def done(result):
            if result.get('checkpoint'):self.project['model']['checkpoint']=result['checkpoint']
            self.record_runtime(result)
            target.update(ready=True,preparation_state='ready',prepared_bounds=bounds,
                prepared_cache_revision=self.service.cache_revision,
                prepared_full_signature=preparation_signature(target,self.project['model']),preparation_progress=[result['count'],result['count']])
            self.refresh_images();self.mark_dirty(background=True);self.log_message(ui_text('tasks.done.008').format(p0=target['name'],p1=result['count'],p2=result['hits']))
        def failed(message):
            if getattr(self.task,'preparation_superseded',False):
                target['preparation_state']='queued' if target['id'] in self.preparation.ids else 'pending'
                target['ready']=False;self.refresh_images();self.mark_dirty(background=True);return
            target['preparation_state']='paused' if ui_text('tasks.error.004') in message else 'failed';target['ready']=False
            self.preparation.paused=True;self.preparation.add([target['id']]);self.refresh_images();self.mark_dirty(background=True)
        self.run(ui_text('tasks.start_preparation.009')+target['name'],lambda t:self.service.preprocess(image,config,bounds,t),done,kind='preparation',on_error=failed)



    def preprocess(self):
        if not self.image or self.task:return
        if not self.image.get('model_recipe'):self.configure_bands();return
        self.queue_preparation();self.preparation.paused=False;self.start_preparation(self.image)

