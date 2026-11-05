"""Qt presentation/controller layer. Heavy work is delegated to services."""
from __future__ import annotations
import copy
from pathlib import Path
from PySide6.QtCore import QTimer, QThreadPool
from PySide6.QtWidgets import QMainWindow
from .domain import new_project
from .model_preferences import application_settings,last_model
from .inference.client import ModelService
from .viewport import ImageView
from .branding import application_icon
from .window_preferences import remember_window, restore_window


from .theme import install_theme
from .workflow import PreparationQueue



from .controllers.actions import WorkbenchActions
from .controllers.tasks import TaskWorkflow
from .controllers.preparation import PreparationWorkflow
from .controllers.control_state import ControlState
from .controllers.projects import ProjectWorkflow
from .controllers.images import ImageWorkflow
from .controllers.models import ModelWorkflow
from .controllers.classes import ClassWorkflow
from .controllers.label_list import LabelListWorkflow
from .controllers.prompts import PromptWorkflow
from .controllers.labels import LabelWorkflow
from .controllers.history import HistoryWorkflow
from .controllers.exports import ExportWorkflow
from .controllers.display import DisplayWorkflow
from .controllers.modes import ModeWorkflow
from .controllers.shutdown import ShutdownWorkflow
from .controllers.reshape import ReshapeWorkflow
from .controllers.manual_polygon import ManualPolygonWorkflow
from .controllers.smoothing import SmoothingWorkflow
from .controllers.project_loading import ProjectLoadingWorkflow
from .controllers.references import ReferenceWorkflow
from .controllers.resources import ResourceWorkflow


class MainWindow(ResourceWorkflow,ReferenceWorkflow,WorkbenchActions,TaskWorkflow,PreparationWorkflow,ControlState,ProjectWorkflow,ImageWorkflow,ModelWorkflow,ClassWorkflow,LabelListWorkflow,PromptWorkflow,HistoryWorkflow,LabelWorkflow,ExportWorkflow,DisplayWorkflow,ModeWorkflow,ShutdownWorkflow,ReshapeWorkflow,ManualPolygonWorkflow,SmoothingWorkflow,ProjectLoadingWorkflow,QMainWindow):
    def __init__(self,project_path=None,recover_latest=False,auto_prepare=True,startup_context=None):
        install_theme()
        super().__init__();self.setWindowTitle('GeoForma');self.setMinimumSize(1024,700)
        self.setWindowIcon(application_icon())
        from .workbench_state import WorkbenchState
        self.settings=application_settings()
        self.runtime_hardware=(getattr(startup_context,'runtime_hardware',None) or {})
        self.state=WorkbenchState(copy.deepcopy(startup_context.project) if startup_context else new_project(last_model(self.settings)))
        self.service=ModelService();self.pool=QThreadPool(self);self.pool.setMaxThreadCount(1);self.render_pool=QThreadPool(self);self.render_pool.setMaxThreadCount(1)
        self.task=None;self.task_kind=None;self.render_task=None;self.render_pending=False;self.render_generation=0;self.shutdown_task=None;self.shutdown_complete=False;self.shutdown_ready=False;self.actions_to_lock=[]
        self.auto_prepare=auto_prepare;self.preparation=PreparationQueue();self.preparing_id=None;self.restoring_project=False
        self.display_reference=None;self.reference_transition_pending=False
        self.storage_pool=QThreadPool(self);self.storage_pool.setMaxThreadCount(1);self.autosave_task=None
        from .project_save_queue import ProjectSaveQueue
        self.project_saves=ProjectSaveQueue()
        self.housekeeping_pool=QThreadPool(self);self.housekeeping_pool.setMaxThreadCount(1);self.housekeeping_task=None
        self.load_pool=QThreadPool(self);self.load_pool.setMaxThreadCount(1);self.loading_task=None;self.project_transition=None
        self.label_index_pool=QThreadPool(self);self.label_index_pool.setMaxThreadCount(1);self.label_index_task=None;self.label_index=None;self.label_index_key=None
        self.view=ImageView()
        from .rendering.smoothing_queue import SmoothingQueue
        self.smoother=SmoothingQueue(self);self.smoother.updated.connect(self.smoothing_updated);self.smoother.error.connect(self.smoothing_error)
        self.smoother.idle.connect(lambda:QTimer.singleShot(0,self.close) if self.closing else None)
        from .ui.label_lookup import LabelLookup
        self.label_lookup=LabelLookup()
        from .rendering.raster_queue import RasterRenderQueue
        from .reference_images import read_display
        self.raster_renderer=RasterRenderQueue(self.render_pool,read_display,self)
        self.raster_renderer.activity.connect(lambda task:setattr(self,'render_task',task));self.raster_renderer.rendered.connect(self.apply_raster);self.raster_renderer.error.connect(self.log_message);self.raster_renderer.idle.connect(self.render_finished)
        self.raster_renderer.error.connect(lambda message:self.view.show_raster_error())
        self.raster_renderer.error.connect(self.reference_render_failed)
        self.prompt_revision=0;self.pending_task_retry=None;self.pending_prefetch_work=None
        self.auto_apply_timer=QTimer(self);self.auto_apply_timer.setSingleShot(True);self.auto_apply_timer.setInterval(35);self.auto_apply_timer.timeout.connect(self.apply_automatically)
        self.view.reshapePoint.connect(self.add_reshape_point);self.view.reshapeFinished.connect(self.finish_reshape);self.view.reshapeUndo.connect(self.undo_reshape_point);self.view.reshapeCancelled.connect(self.cancel_reshape)
        self.view.reshapeTarget.connect(self.pick_reshape_target)
        self.view.polygonPoint.connect(self.add_manual_vertex);self.view.polygonFinished.connect(self.finish_manual_polygon)
        self.view.polygonUndo.connect(self.undo_manual_vertex);self.view.polygonCancelled.connect(self.cancel_manual_polygon)
        self.build_actions();self.build_left();self.build_right();self.build_bottom();self.setAcceptDrops(True)
        self.raster_renderer.activity.connect(self.background_activity.raster_changed)
        self.smoother.activity.connect(self.background_activity.smoothing_changed)
        self.view.point.connect(self.add_point);self.view.box.connect(self.add_box);self.view.selected.connect(self.select_label)
        self.view.selection.connect(self.select_items)
        self.render_timer=QTimer(self);self.render_timer.setSingleShot(True);self.render_timer.setInterval(150);self.render_timer.timeout.connect(self.request_render);self.view.viewportChanged.connect(self.render_timer.start)
        self.view.viewportChanged.connect(self.raster_renderer.viewport_changed)
        self.autosave_timer=QTimer(self);self.autosave_timer.setInterval(15000);self.autosave_timer.timeout.connect(self.autosave);self.autosave_timer.start()
        self.autosave_debounce=QTimer(self);self.autosave_debounce.setSingleShot(True);self.autosave_debounce.setInterval(400)
        self.autosave_debounce.timeout.connect(lambda:self.autosave())
        self.refresh_classes();self.refresh_images();self.update_controls();self.refresh_labels()
        restore_window(self,self.settings)
        self._startup_actions=(project_path,recover_latest,auto_prepare) if startup_context is not None else None
        if startup_context is None:
            if project_path:QTimer.singleShot(0,lambda:self.request_project_open(project_path,recover_latest))
            if auto_prepare:
                QTimer.singleShot(350,self.remind_resources);QTimer.singleShot(5000,self,self.start_background_cleanup)

    def showEvent(self,event):
        super().showEvent(event)
        actions=getattr(self,'_startup_actions',None)
        if actions is not None:
            self._startup_actions=None;path,recover,prepare=actions
            if path:QTimer.singleShot(0,self,lambda:self.request_project_open(path,recover))
            if prepare:
                QTimer.singleShot(350,self,self.remind_resources);QTimer.singleShot(5000,self,self.start_background_cleanup)

    def current_labels(self):
        # Only confirmed records participate in the workbench.
        return self.label_lookup.confirmed_for_image(self.project['labels'],self.image['id']) if self.image else ()

    def dragEnterEvent(self,event):
        from .image_list import IMPORT_SUFFIXES
        from .operation_state import can_start_operation
        if can_start_operation(self) and self.reshape_session is None and any(u.isLocalFile() and Path(u.toLocalFile()).suffix.lower() in IMPORT_SUFFIXES for u in event.mimeData().urls()):event.acceptProposedAction()

    def dropEvent(self,event):
        from .image_list import IMPORT_SUFFIXES
        from .operation_state import can_start_operation
        files=[u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile() and Path(u.toLocalFile()).suffix.lower() in IMPORT_SUFFIXES]
        if files and can_start_operation(self) and self.reshape_session is None:self.import_paths(files);event.acceptProposedAction()

    def closeEvent(self,event):
        self.close_application(event)
        if event.isAccepted():remember_window(self,self.settings)


    # Explicit state bridge keeps the public workbench API stable.
    def _set_project(self,value):
        self.state.project=value
        self.state.label_indexes.clear()
        self.label_index=None;self.label_index_key=None
        if hasattr(self,'label_lookup'):self.label_lookup.clear()
        if hasattr(self,'view'):
            self.view.path_cache.clear();self.view.layers.pixmap_cache.clear()
    project = property(lambda self: self.state.project, _set_project)
    project_path = property(lambda self: self.state.project_path, lambda self, value: setattr(self.state, 'project_path', value))
    image = property(lambda self: self.state.image, lambda self, value: setattr(self.state, 'image', value))
    draft = property(lambda self: self.state.draft, lambda self, value: setattr(self.state, 'draft', value))
    reshape_session = property(lambda self: self.state.reshape_session, lambda self, value: setattr(self.state, 'reshape_session', value))
    prompt_undo = property(lambda self: self.state.prompt_undo, lambda self, value: setattr(self.state, 'prompt_undo', value))
    prompt_redo = property(lambda self: self.state.prompt_redo, lambda self, value: setattr(self.state, 'prompt_redo', value))
    label_undo = property(lambda self: self.state.label_undo, lambda self, value: setattr(self.state, 'label_undo', value))
    label_redo = property(lambda self: self.state.label_redo, lambda self, value: setattr(self.state, 'label_redo', value))
    selected_id = property(lambda self: self.state.selected_id, lambda self, value: setattr(self.state, 'selected_id', value))
    selected_ids = property(lambda self: self.state.selected_ids, lambda self, value: setattr(self.state, 'selected_ids', value))
    selected_points = property(lambda self: self.state.selected_points, lambda self, value: setattr(self.state, 'selected_points', value))
    image_sessions = property(lambda self: self.state.image_sessions, lambda self, value: setattr(self.state, 'image_sessions', value))
    runtime_status = property(lambda self: self.state.runtime_status, lambda self, value: setattr(self.state, 'runtime_status', value))
    dirty = property(lambda self: self.state.dirty, lambda self, value: setattr(self.state, 'dirty', value))
    dirty_revision = property(lambda self: self.state.dirty_revision, lambda self, value: setattr(self.state, 'dirty_revision', value))
    project_epoch = property(lambda self: self.state.project_epoch, lambda self, value: setattr(self.state, 'project_epoch', value))
    closing = property(lambda self: self.state.closing, lambda self, value: setattr(self.state, 'closing', value))
    last_error = property(lambda self: self.state.last_error, lambda self, value: setattr(self.state, 'last_error', value))
    mode_index = property(lambda self: self.state.mode_index, lambda self, value: setattr(self.state, 'mode_index', value))
    mode_histories = property(lambda self: self.state.mode_histories, lambda self, value: setattr(self.state, 'mode_histories', value))
    tool_modes = property(lambda self: self.state.tool_modes, lambda self, value: setattr(self.state, 'tool_modes', value))
    model_warmup_signature = property(lambda self: self.state.model_warmup_signature, lambda self, value: setattr(self.state, 'model_warmup_signature', value))
    label_indexes = property(lambda self: self.state.label_indexes, lambda self, value: setattr(self.state, 'label_indexes', value))
