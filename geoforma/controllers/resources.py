"""Resource readiness is independent of projects, tools, and render transitions."""
from PySide6.QtCore import QTimer
import sys
from .. import native_runtime
from ..resource_state import snapshot
from ..ui.text import ui_text

class ResourceWorkflow:
    def start_background_cleanup(self):
        if self.closing or self.housekeeping_task is not None:return
        if getattr(getattr(self,'resource_dialog',None),'migration_active',False):
            QTimer.singleShot(60000,self,self.start_background_cleanup);return
        from ..resource_migration import pending_migration
        try:
            if pending_migration():
                QTimer.singleShot(60000,self,self.start_background_cleanup);return
        except (OSError,ValueError,RuntimeError):return
        from ..resource_location import require_resource_dir
        from ..housekeeping import clean_download_remnants
        from ..tasks import Task
        try:root=require_resource_dir()
        except (OSError,ValueError,RuntimeError) as error:
            self.log_message('资源目录不可用，暂不清理：'+str(error))
            QTimer.singleShot(24*60*60*1000,self,self.start_background_cleanup);return
        task=Task(lambda work:clean_download_remnants(root,work,apply=True))
        self.housekeeping_task=task
        def finished():
            self.housekeeping_task=None
            if self.closing:QTimer.singleShot(0,self.close)
            else:QTimer.singleShot(24*60*60*1000,self,self.start_background_cleanup)
        def failed(message):
            if not task.cancel_event.is_set():self.log_message('清理旧下载残留失败：'+message)
        task.signals.error.connect(failed);task.signals.finished.connect(finished)
        self.housekeeping_pool.start(task)

    def open_data_directory(self):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        from ..domain import data_dir
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(data_dir()))):
            self.log_message('无法打开数据目录：'+str(data_dir()))
            self.statusBar().report_error('无法打开数据目录，请检查目录权限或使用文件管理器访问。',source='open_data')

    def ensure_model_resources(self):
        from ..resource_migration import pending_migration
        try:pending=bool(pending_migration())
        except (OSError,ValueError,RuntimeError):pending=True
        if pending:
            self.preparation.paused=True;self.statusBar().showMessage('请先完成资源迁移。',6000)
            if not getattr(self,'resource_reminded',False):
                self.resource_reminded=True;QTimer.singleShot(0,self.configure_resources)
            return False
        if not native_runtime.lightweight() and not getattr(sys,'frozen',False):return True
        if snapshot(self.project['model'])['ready']:
            self.resource_reminded=False;return True
        self.preparation.paused=True
        self.statusBar().showMessage(ui_text('resources.missing_hint'),6000)
        if not getattr(self,'resource_reminded',False):
            self.resource_reminded=True;QTimer.singleShot(0,self.configure_resources)
        return False

    def remind_resources(self):
        if self.closing or self.loading_task or self.project_transition or getattr(self,'resource_dialog',None) is not None:return
        from ..resource_migration import pending_migration
        try:pending=bool(pending_migration())
        except (OSError,ValueError,RuntimeError):pending=True
        if pending:
            self.resource_reminded=True;self.configure_resources();return
        if (native_runtime.lightweight() or getattr(sys,'frozen',False)) and not snapshot(self.project['model'])['ready']:
            self.resource_reminded=True;self.configure_resources()

    def configure_resources(self):
        dialog=getattr(self,'resource_dialog',None)
        if dialog is not None:dialog.show();dialog.raise_();dialog.activateWindow();return
        if self.closing or self.loading_task or self.project_transition:return
        from ..ui.resources import ResourceDialog
        dialog=ResourceDialog(self);self.resource_dialog=dialog
        def finished(_):
            self.resource_dialog=None;dialog.deleteLater()
            if self.closing:return
            if snapshot(self.project['model'])['ready']:
                self.resource_reminded=False
                self.model_warmup_signature=None;self.preparation.paused=False
                self.queue_preparation()
            self.update_controls()
        dialog.finished.connect(finished);dialog.show()
