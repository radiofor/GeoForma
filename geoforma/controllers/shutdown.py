"""Responsive exit: workers finish before the model process is released."""
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox
from ..tasks import Task
from ..ui.text import ui_text

class ShutdownWorkflow:
    def abort_shutdown(self):
        self.closing=False;self.shutdown_ready=False
        self.raster_renderer.closed=False
        self.smoother.closed=False
        if self.image:self.render_timer.start()
        self.autosave_timer.start();self.update_controls()

    def close_application(self,event):
        if getattr(self,'shutdown_complete',False):
            event.accept();return
        if getattr(self,'shutdown_task',None):event.ignore();return
        self.auto_apply_timer.stop();self.render_timer.stop();self.autosave_timer.stop();self.autosave_debounce.stop();self.invalidate_preview()
        self.smoother.close()
        if self.label_index_task:self.label_index_task.cancel()
        if self.loading_task:self.loading_task.cancel()
        if self.housekeeping_task:self.housekeeping_task.cancel()
        if self.project_transition:self.finish_project_transition(False)
        self.remember_current_model();was_closing=self.closing
        if self.autosave() is False:
            if not was_closing:
                self.abort_shutdown()
                QMessageBox.warning(self,ui_text('projects.failed.007'),ui_text('projects.failed.008'))
            event.ignore();return
        pending=bool(self.task or self.render_task or self.label_index_task or self.autosave_task or self.smoother.task or self.loading_task or self.housekeeping_task)
        pools=(self.pool,self.render_pool,self.label_index_pool,self.storage_pool,self.smoother.pool,self.load_pool,self.housekeeping_pool)
        if pending or any(pool.activeThreadCount() for pool in pools):
            self.closing=True;self.cancel();event.ignore()
            if not pending:QTimer.singleShot(25,self.close)
            return
        self.raster_renderer.close()
        if self.service.process is None:
            self.service.close();self.finish_shutdown(event);return
        # Process joins and GPU cleanup must not freeze Qt.
        self.closing=True;event.ignore()
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
        self.shutdown_complete=True
        if event is not None:event.accept()
        else:self.close()
