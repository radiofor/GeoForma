"""Responsive exit: workers finish before the model process is released."""
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox
from ..tasks import Task
from ..ui.text import ui_text


class ShutdownWorkflow:
    def shutdown_step(self):
        if self.autosave_task:return 0
        if self.task or self.render_task or self.candidate_task or self.smoother.task or self.loading_task or self.housekeeping_task:return 1
        return 2

    def shutdown_phase(self):return ui_text(('shutdown.saving','shutdown.waiting','shutdown.releasing')[self.shutdown_step()])

    def show_shutdown(self):
        from ..ui.shutdown_dialog import ShutdownDialog
        if getattr(self,'shutdown_dialog',None) is None:self.shutdown_dialog=ShutdownDialog(self,self.shutdown_phase,self.shutdown_step)
        self.shutdown_dialog.show();self.shutdown_dialog.raise_()

    def abort_shutdown(self):
        self.closing=False;self.shutdown_ready=False;self.shutdown_finishing=False
        if getattr(self,'shutdown_dialog',None):self.shutdown_dialog.finish('failed');self.shutdown_dialog=None
        self.raster_renderer.closed=False
        self.smoother.closed=False
        if self.image:self.render_timer.start()
        self.autosave_timer.start();self.update_controls()

    def close_application(self,event):
        if getattr(self,'shutdown_complete',False):
            if getattr(self,'shutdown_dialog',None):self.shutdown_dialog.hide()
            event.accept();return
        if getattr(self,'shutdown_task',None) or getattr(self,'shutdown_finishing',False):event.ignore();return
        self.auto_apply_timer.stop();self.render_timer.stop();self.autosave_timer.stop();self.autosave_debounce.stop();self.invalidate_preview()
        self.smoother.close()
        if self.candidate_task:self.candidate_task.cancel()
        if self.loading_task:self.loading_task.cancel()
        if self.housekeeping_task:self.housekeeping_task.cancel()
        if self.project_transition:self.finish_project_transition(False)
        self.remember_current_model();self.autosave()
        pending=bool(self.task or self.render_task or self.candidate_task or self.autosave_task or self.smoother.task or self.loading_task or self.housekeeping_task)
        pools=(self.pool,self.render_pool,self.candidate_pool,self.storage_pool,self.smoother.pool,self.load_pool,self.housekeeping_pool)
        if pending or any(pool.activeThreadCount() for pool in pools):
            self.closing=True;self.show_shutdown();self.cancel();self.task_text.setText(ui_text('shutdown.waiting'));event.ignore()
            if not pending:QTimer.singleShot(25,self.close)
            return
        self.raster_renderer.close()
        if self.service.process is None:
            self.service.close();self.finish_shutdown(event);return
        # Process joins and GPU cleanup must not freeze the animation or Qt.
        self.closing=True;self.show_shutdown();event.ignore()
        task=Task(lambda t:self.service.close());self.shutdown_task=task
        task.signals.result.connect(lambda _:setattr(self,'shutdown_ready',True))
        def failed(message):
            self.log_message(message);self.abort_shutdown()
            QMessageBox.warning(self,ui_text('shutdown.title'),ui_text('shutdown.failed'))
        def finished():
            self.shutdown_task=None
            if getattr(self,'shutdown_ready',False):self.finish_shutdown()
        task.signals.error.connect(failed);task.signals.finished.connect(finished);self.storage_pool.start(task)

    def finish_shutdown(self,event=None):
        # A delayed resource reminder can otherwise open after the main window
        # has closed, keeping the process alive without a workbench.
        self.closing=True
        resource=getattr(self,'resource_dialog',None)
        if resource is not None:resource.close()
        dialog=getattr(self,'shutdown_dialog',None)
        if dialog is None:
            self.shutdown_complete=True
            if event is not None:event.accept()
            else:self.close()
            return
        if event is not None:event.ignore()
        if getattr(self,'shutdown_finishing',False):return
        self.shutdown_finishing=True
        def complete():
            self.shutdown_complete=True;self.shutdown_finishing=False;self.close()
        dialog.finish(on_finished=complete)
