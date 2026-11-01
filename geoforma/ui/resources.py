"""Stable settings surface for automatic and offline resource configuration."""
import copy
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,QUrl,QSize
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QWidget,
    QPushButton,QPlainTextEdit,QFileDialog,QSizePolicy,QMenu,QTabWidget,QTabBar,QMessageBox)
from .. import native_runtime
from ..model_catalog import MODELS,model_spec
from ..resource_state import inventory
from ..weights import install_checkpoint,checkpoint_resource
from ..operation_state import can_start_operation
from ..resource_links import model_home,size_text,PYTORCH_HOME
from ..error_messages import user_message
from .resource_manual import ManualResourceDialog
from .resource_details import ResourceDetails
from .modal import dialog_result
from .progress_bar import TaskProgressBar
from .centered_combo import CenteredComboBox as QComboBox
from .controls import ElidedLabel
from .text import ui_text


class ResourceTabBar(QTabBar):
    """Divide the resource row evenly without changing other tab bars."""
    def tabSizeHint(self,index):
        hint=super().tabSizeHint(index)
        owner=self.parentWidget()
        return QSize(max(1,owner.contentsRect().width()//max(1,self.count())),hint.height())

    def minimumTabSizeHint(self,index):return self.tabSizeHint(index)


class ResourceTabs(QTabWidget):
    def __init__(self,parent=None):
        super().__init__(parent);bar=ResourceTabBar(self);bar.setExpanding(True);self.setTabBar(bar)

    def resizeEvent(self,event):
        super().resizeEvent(event);self.tabBar().setFixedWidth(self.contentsRect().width())


class ResourceDialog(QDialog):
    def __init__(self,window):
        super().__init__(window);self.window=window;self.task=None;self.setWindowTitle('资源配置')
        self.setWindowModality(Qt.WindowModality.ApplicationModal);self.resize(760,620);self.setMinimumSize(680,580)
        layout=QVBoxLayout(self);layout.setContentsMargins(20,18,20,16);layout.setSpacing(10)
        title=QLabel(ui_text('resources.title'));title.setProperty('role','dialogTitle');title.setFixedHeight(28);layout.addWidget(title)
        card=QWidget();card.setObjectName('rasterInfo');form=QFormLayout(card);form.setContentsMargins(14,10,14,10)
        self.weight_status=ElidedLabel();self.weight_status.setFixedHeight(24)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.runtime_status=ElidedLabel();self.runtime_status.setFixedHeight(24)
        if native_runtime.lightweight():
            label=QLabel('当前运行库');label.setProperty('role','muted');form.addRow(label,self.runtime_status)
        for caption,value in (('当前模型',self.weight_status),):
            label=QLabel(caption);label.setProperty('role','muted');form.addRow(label,value)
        layout.addWidget(card)
        location_row=QHBoxLayout();location_row.setSpacing(8)
        location_label=QLabel('资源目录');location_label.setProperty('role','muted');location_row.addWidget(location_label)
        self.location_path=ElidedLabel();self.location_path.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
        self.location_path.setFixedHeight(32);self.location_path.setAccessibleName('资源目录');location_row.addWidget(self.location_path,1)
        self.location_choose=QPushButton('选择目录');self.location_choose.setAutoDefault(False);self.location_choose.clicked.connect(self.choose_location);location_row.addWidget(self.location_choose)
        self.location_reset=QPushButton('恢复默认');self.location_reset.setAutoDefault(False);self.location_reset.clicked.connect(self.reset_location);location_row.addWidget(self.location_reset)
        layout.addLayout(location_row)
        location_hint=QLabel('运行库、权重、缓存、日志和未命名工作恢复文件存放在此；切换目录会迁移现有资源。')
        location_hint.setProperty('role','muted');location_hint.setWordWrap(True);layout.addWidget(location_hint)
        self.tabs=ResourceTabs();layout.addWidget(self.tabs)
        self.profile=QComboBox();self.runtime_detail=ResourceDetails()
        self.runtime_download=QPushButton('自动下载并配置');self.runtime_manual=QPushButton('手动配置')
        if native_runtime.lightweight():
            runtime=QWidget();runtime_layout=QVBoxLayout(runtime);runtime_layout.setContentsMargins(14,14,14,14);runtime_layout.setSpacing(12)
            for key,spec in native_runtime.catalog()['profiles'].items():self.profile.addItem(spec['title'],key)
            if getattr(window,'runtime_hardware',{}).get('nvidia') and window.project['model'].get('device')!='cpu':self.profile.setCurrentIndex(self.profile.findData('cu126'))
            runtime_layout.addWidget(self.profile);runtime_layout.addWidget(self.runtime_detail)
            row_buttons=QHBoxLayout();self.runtime_download.setObjectName('primary');self.runtime_download.setProperty('feedback','primary');self.runtime_manual.setProperty('feedback','import')
            for button in (self.runtime_download,self.runtime_manual):row_buttons.addWidget(button,1)
            runtime_layout.addLayout(row_buttons);self.tabs.addTab(runtime,'PyTorch 运行库')
            self.profile.currentIndexChanged.connect(self.refresh)
            self.runtime_download.clicked.connect(lambda:self.install_runtime())
            self.runtime_manual.clicked.connect(lambda:self.manual_setup(native_runtime.download_wheels(self.profile.currentData()),PYTORCH_HOME,self.import_runtime,'PyTorch · '+native_runtime.profile(self.profile.currentData())['title']))
        weight=QWidget();weight.setObjectName('modelResources');self.tabs.addTab(weight,'模型权重')
        row=QVBoxLayout(weight);row.setContentsMargins(14,14,14,14);row.setSpacing(12)
        heading=QLabel('模型权重');heading.setProperty('role','sectionTitle');row.addWidget(heading);self.model=QComboBox()
        for spec in MODELS:self.model.addItem(spec['title']+' · '+size_text(spec['bytes']),spec['id'])
        selected=model_spec(window.project['model']['variant'],window.project['model'].get('backend','sam'))
        self.model.setCurrentIndex(self.model.findData(selected['id']));row.addWidget(self.model)
        self.weight_detail=ResourceDetails();row.addWidget(self.weight_detail)
        buttons=QHBoxLayout();self.weight_download=QPushButton('自动下载并配置');self.weight_manual=QPushButton('手动配置')
        self.weight_download.setObjectName('primary')
        for button in (self.weight_download,self.weight_manual):buttons.addWidget(button,1)
        row.addLayout(buttons)
        self.weight_download.setProperty('feedback','primary');self.weight_manual.setProperty('feedback','import')
        self.model.currentIndexChanged.connect(self.refresh)
        self.weight_download.clicked.connect(lambda:self.install_weight())
        self.weight_manual.clicked.connect(lambda:self.manual_setup([checkpoint_resource(self.selected_model())],model_home(self.selected_model()),self.import_weight,'模型权重 · '+self.selected_model()['title']))
        self.phase=ElidedLabel(ui_text('resources.idle'));self.phase.setFixedHeight(28);self.phase.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed);layout.addWidget(self.phase)
        self.progress=TaskProgressBar(expanding=True);layout.addWidget(self.progress)
        self.details_heading=QLabel(ui_text('resources.record'));self.details_heading.setProperty('role','sectionTitle');self.details_heading.setFixedHeight(18);layout.addWidget(self.details_heading)
        self.details=QPlainTextEdit();self.details.setReadOnly(True);self.details.setFixedHeight(92)
        self.details.setAccessibleName(ui_text('resources.record'));layout.addWidget(self.details)
        bottom=QHBoxLayout();self.more_button=QPushButton(ui_text('resources.more'));self.more_button.setProperty('feedback','dialog')
        self.more_menu=QMenu(self.more_button);self.more_menu.setToolTipsVisible(True)
        self.open_folder_action=self.more_menu.addAction(ui_text('resources.open_folder'));self.open_folder_action.triggered.connect(self.open_location)
        self.clear_cache_action=self.more_menu.addAction('清理运行库下载缓存' if native_runtime.lightweight() else '清理旧运行库下载缓存');self.clear_cache_action.setToolTip(ui_text('resources.cache_hint'))
        self.clear_cache_action.triggered.connect(lambda:self.run('清理下载缓存',lambda task:native_runtime.NativeRuntimeManager().clear_downloads(task),completion=ui_text('resources.cache_complete')))
        self.more_button.setMenu(self.more_menu);bottom.addWidget(self.more_button)
        self.resume_migration_button=QPushButton('继续迁移');self.resume_migration_button.clicked.connect(self.resume_migration);self.resume_migration_button.hide();bottom.addWidget(self.resume_migration_button)
        bottom.addStretch(1);self.stop_button=QPushButton(ui_text('resources.stop'));self.stop_button.setProperty('feedback','cancel')
        self.stop_button.setToolTip(ui_text('resources.stop_hint'));self.stop_button.clicked.connect(self.stop);self.stop_button.setEnabled(False);bottom.addWidget(self.stop_button)
        self.close_button=QPushButton('关闭');self.close_button.clicked.connect(self.accept);bottom.addWidget(self.close_button);layout.addLayout(bottom)
        for button in (self.more_button,self.stop_button,self.close_button):button.setFixedSize(88,32);button.setAutoDefault(False)
        self.setMinimumHeight(max(self.minimumHeight(),layout.minimumSize().height()))
        self.migration_active=False;self._migration_result=None;self._migration_applied=False
        self.timer=QTimer(self);self.timer.setInterval(250);self.timer.timeout.connect(self.sync_busy);self.timer.start();self.reload_inventory()

    def selected_model(self):return next(spec for spec in MODELS if spec['id']==self.model.currentData())

    def reload_inventory(self):
        from ..resource_location import current_resource_dir,require_resource_dir
        from ..resource_migration import pending_migration
        try:self.pending_migration=pending_migration()
        except (OSError,ValueError,RuntimeError) as error:
            self.pending_migration={'error':str(error)}
        self.resume_migration_button.setVisible(bool(self.pending_migration))
        if self.pending_migration:
            self.location_valid=False;self.location_path.setText('有未完成的资源迁移')
            self.phase.setText('资源迁移未完成，请继续迁移')
            self.sync_busy();return
        try:
            path=str(current_resource_dir());require_resource_dir()
        except (OSError,ValueError,RuntimeError) as error:
            self.location_valid=False;self.location_path.setText('资源目录不可用：'+locals().get('path',''));self.location_path.setToolTip(str(error))
            self.phase.setText('资源目录不可用，请重新选择或恢复默认')
            self.sync_busy();return
        self.location_valid=True;self.location_path.setText(path);self.location_path.setToolTip(path)
        self.inventory=inventory(self.window.project['model']);self.refresh()

    @staticmethod
    def weight_state_text(state):
        return ui_text({'configured':'resources.configured','missing':'resources.missing',
            'local':'resources.local','incomplete':'resources.incomplete','unavailable':'resources.unavailable'}[state['availability']])

    def refresh(self):
        state=self.inventory;current=state['current_model']
        if native_runtime.lightweight():
            runtime=state['runtime'];self.runtime_status.setText(runtime.get('title','未配置'))
            blocked=self.profile.blockSignals(True)
            try:
                for index in range(self.profile.count()):
                    item=state['profiles'][self.profile.itemData(index)]
                    status='已配置' if item['configured'] else '未配置'
                    if item['current']:status+=' · 当前使用'
                    self.profile.setItemText(index,'PyTorch '+item['version'].split('+')[0]+' · '+item['title']+' · '+status)
            finally:self.profile.blockSignals(blocked)
            item=state['profiles'][self.profile.currentData()]
            status=('已配置' if item['configured'] else '未配置 · 下载 '+size_text(item['bytes']))
            note='CUDA 加速 · 支持 CPU 回退 · 需兼容的显卡驱动' if item['key']=='cu126' else '适用于 CPU，无需 NVIDIA 显卡'
            self.runtime_detail.setText(status+'\n'+note)
            self.runtime_download.setText('切换到此运行库' if item['configured'] and not item['current'] else '重新配置' if item['current'] else '自动下载并配置')
        self.weight_status.setText(current['title']);self.weight_status.setToolTip(state['models'][current['id']]['path'])
        blocked=[(combo,combo.blockSignals(True)) for combo in (self.model,)]
        try:
            for index in range(self.model.count()):
                item=state['models'][self.model.itemData(index)]
                text=item['spec']['title']+' · '+self.weight_state_text(item)
                if item['current']:text+=' · '+ui_text('resources.current_model')
                if self.model.itemText(index)!=text:self.model.setItemText(index,text)
                self.model.setItemData(index,item['path'],Qt.ItemDataRole.ToolTipRole)
        finally:
            for combo,previous in blocked:combo.blockSignals(previous)
        item=state['models'][self.model.currentData()];spec=item['spec'];status=self.weight_state_text(item)
        if item['current']:status+=' · '+ui_text('resources.current_model')
        if item['availability'] in ('missing','incomplete'):status+=' · 下载 '+size_text(spec['bytes'])
        note=ui_text('resources.unavailable_hint' if item['availability']=='unavailable' else 'resources.local_hint' if item['availability']=='local' else 'resources.weight_hint')
        self.weight_detail.setText('\n'.join((status,Path(item['path']).name,note)));self.weight_detail.setToolTip(item['path'])
        self.weight_download.setText(ui_text('resources.reconfigure' if item['availability']=='configured' else 'resources.download_configure'))
        self.sync_busy()

    def sync_busy(self):
        available=can_start_operation(self.window) and self.task is None
        resources_available=available and getattr(self,'location_valid',False)
        for control in (self.weight_download,self.weight_manual,self.model,self.clear_cache_action,self.runtime_download,self.runtime_manual,self.profile):control.setEnabled(resources_available)
        change_available=available and not getattr(self.window,'housekeeping_task',None) and not getattr(self.window,'autosave_task',None)
        for control in (self.location_choose,self.location_reset):control.setEnabled(change_available and not getattr(self,'pending_migration',None))
        self.resume_migration_button.setEnabled(change_available and bool(getattr(self,'pending_migration',None)))
        self.stop_button.setEnabled(self.task is not None and self.progress.model.state.can_cancel and not self.task.cancel_event.is_set())
        self.close_button.setEnabled(self.task is None)
        self.close_button.setToolTip(ui_text('resources.close_busy') if self.task is not None else '')

    def run(self,title,work,callback=None,*,reset_model=False,completion=None):
        if not can_start_operation(self.window):return
        self.details.clear();self.last_stage=None;self.phase.setText(title);self.progress.model.begin(title,'resources',cancellable=True)
        def done(value):
            if callback:callback(value)
            result_text=completion or ui_text('resources.complete')
            self.phase.setText(result_text);self.details.appendPlainText(result_text);self.progress.model.finish('complete');self.sync_busy()
        def failed(message):
            if self.task and self.task.cancel_event.is_set():self.finish_stopped()
            else:
                self.phase.setText(ui_text('resources.failed'));self.details.setPlainText(user_message(message));self.progress.model.finish('failed')
        def finished():
            # A stop can arrive after the worker emits a result but before its
            # queued callback. The workbench then suppresses the result callback.
            if self.progress.phase=='running':
                if self.task and self.task.cancel_event.is_set():self.finish_stopped()
                else:self.phase.setText(ui_text('resources.failed'));self.progress.model.finish('failed')
            self.task=None
            if self.migration_active and self._migration_result is not None and not self._migration_applied:
                self.migration_done(self._migration_result)
            self.migration_active=False;self.reload_inventory()
        def install(task):
            if reset_model:self.window.service.close()
            task.check();return work(task)
        if reset_model:self.window.runtime_status=None;self.window.model_warmup_signature=None
        if self.window.run(title,install,done,kind='resource_install',on_error=failed,on_finished=finished):
            self.task=self.window.task;self.task.signals.progress.connect(self.report);self.sync_busy()
            return True
        return False

    def report(self,current,total,text):
        if not self.progress.model.report(current,total,text):return
        self.phase.setText((f'{round(100*current/total)}% · ' if total else '')+text);self.phase.setToolTip(text)
        # Persistent milestone log, not thousands of per-chunk lines.
        stage=next((name for name in ('下载','校验','安装','配置运行库','验证运行库','运行库已就绪') if name in text),text)
        if stage!=getattr(self,'last_stage',None):self.details.appendPlainText(text);self.last_stage=stage

    def install_weight(self,source=None):
        spec=copy.deepcopy(self.selected_model())
        def done(path):
            current=model_spec(self.window.project['model']['variant'],self.window.project['model'].get('backend','sam'))
            if current['id']==spec['id']:
                self.window.project['model']['checkpoint']=path;self.window.remember_current_model();self.window.mark_dirty()
        self.run('配置 '+spec['title'],lambda task:install_checkpoint(spec,task,source),done)

    def install_runtime(self,sources=None):
        key=self.profile.currentData()
        self.run('配置 PyTorch 运行库',lambda task:native_runtime.NativeRuntimeManager().install(key,task,sources),reset_model=True)

    def import_runtime(self):
        paths,_=QFileDialog.getOpenFileNames(self,'导入 PyTorch 运行库','','Python wheel (*.whl)')
        if paths:self.install_runtime(paths)

    def import_weight(self):
        path,_=QFileDialog.getOpenFileName(self,ui_text('resources.import_weight'),'','模型权重 (*.pt *.pth)')
        if path:self.install_weight(path)

    def manual_setup(self,files,homepage,importer,caption):
        accepted,_=dialog_result(ManualResourceDialog(self,files,homepage,caption))
        if accepted:importer()

    def open_location(self):
        from ..resource_location import require_resource_dir
        try:path=require_resource_dir()
        except (OSError,ValueError,RuntimeError) as error:
            self.details.appendPlainText(str(error));return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            self.details.appendPlainText(ui_text('resources.open_folder_failed'))

    def change_location(self, parent=None, *, reset=False):
        if not can_start_operation(self.window) or self.task is not None or getattr(self.window,'housekeeping_task',None) or getattr(self.window,'autosave_task',None):return
        if getattr(self,'pending_migration',None):return
        if self.window.dirty and (self.window.project_path or self.window.project.get('images') or self.window.project.get('labels')):
            self.phase.setText('正在保存工作，完成后请重新选择资源目录');self.window.autosave();return
        from ..resource_migration import migrate_resources,migrate_to_default
        self.window.preparation.paused=True
        self.migration_active=True;self._migration_result=None;self._migration_applied=False
        snapshot=copy.deepcopy(self.window.project)
        if not self.run('迁移资源',lambda task:self.migration_work(task,snapshot,lambda:migrate_to_default(task) if reset else migrate_resources(parent,task)),
                        self.migration_done,reset_model=True,completion='资源迁移完成'):self.migration_active=False

    def migration_work(self,task,snapshot,operation):
        result=operation();self._migration_result=result
        if not isinstance(result,dict) or not result.get('destination'):return result
        from ..cache_recovery import remap_migrated_checkpoint,reconcile_prepared
        from ..atomic_io import read_json
        destination=Path(result['destination'])
        try:
            changed=remap_migrated_checkpoint(snapshot)
            owner=read_json(destination/'cache'/'active-project.json')
            if changed and owner.get('owner')==snapshot.get('cache_id'):
                reconcile_prepared(snapshot,destination,owner.get('revision'),task)
            result['reconciled_project']=snapshot
        except (OSError,ValueError,RuntimeError):pass
        return result

    def migration_done(self,result):
        self._migration_applied=True
        if isinstance(result,dict) and result.get('source') and result.get('destination'):
            from ..cache_recovery import remap_migrated_checkpoint,remap_migrated_path
            if remap_migrated_checkpoint(self.window.project):
                self.window.remember_current_model();self.window.mark_dirty()
            prepared=result.get('reconciled_project')
            if isinstance(prepared,dict):
                images={image.get('id'):image for image in prepared.get('images',[])}
                for image in self.window.project.get('images',[]):
                    verified=images.get(image.get('id'),{})
                    if verified.get('prepared_full_signature'):
                        image['prepared_full_signature']=verified['prepared_full_signature']
            remembered=self.window.settings.value('recovery/last_work','')
            updated=remap_migrated_path(remembered,'recoveries') if remembered else None
            if updated:self.window.settings.setValue('recovery/last_work',str(updated))
        self.window.model_warmup_signature=None
        self.window.update_controls()

    def resume_migration(self):
        if not getattr(self,'pending_migration',None) or getattr(self.window,'housekeeping_task',None) or getattr(self.window,'autosave_task',None):return
        from ..resource_migration import resume_migration
        self.window.preparation.paused=True
        self.migration_active=True;self._migration_result=None;self._migration_applied=False
        snapshot=copy.deepcopy(self.window.project)
        if not self.run('继续迁移资源',lambda task:self.migration_work(task,snapshot,lambda:resume_migration(task)),self.migration_done,reset_model=True,completion='资源迁移完成'):self.migration_active=False

    def choose_location(self):
        from ..resource_location import current_resource_dir
        try:start=str(current_resource_dir().parent)
        except (OSError,ValueError,RuntimeError):start=str(Path.home())
        parent=QFileDialog.getExistingDirectory(self,'选择资源存放位置',start)
        if parent:self.change_location(parent)

    def reset_location(self):self.change_location(reset=True)

    def stop(self):
        if self.task is not None and self.progress.model.request_cancel(ui_text('resources.cancelling')):
            self.task.cancel();self.phase.setText(ui_text('resources.cancelling'));self.sync_busy()

    def finish_stopped(self):
        self.phase.setText(ui_text('resources.cancelled'))
        self.details.appendPlainText('迁移已暂停；如有未完成记录，请点击“继续迁移”。' if self.migration_active else ui_text('resources.stopped_hint'))
        self.progress.model.finish('cancelled',ui_text('resources.cancelled'))

    def done(self,result):
        if self.task is not None:return
        self.timer.stop();super().done(result)

    def closeEvent(self,event):
        if self.task is not None:event.ignore();return
        super().closeEvent(event)
