"""Asynchronous bootstrap with a painted, completed handoff to the workbench."""
from dataclasses import dataclass
from pathlib import Path
import tempfile
import traceback

from PySide6.QtCore import QObject, QSettings, QThread, QTimer, Qt, Signal, Slot, QRectF
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMessageBox

from .branding import application_icon
from .distribution import VERSION
from .theme import draw_grid_pattern
from .ui.progress_bar import TaskProgressBar,COMPLETION_HOLD_MS


@dataclass(frozen=True)
class StartupContext:
    data_root: Path
    project: dict
    window_type: type
    runtime_hardware: dict | None = None


class StartupCancelled(Exception):
    pass


def prepare_startup(progress, check):
    """Worker-only preparation; Qt widgets and inference belong to other owners."""
    check()
    progress(1, '检查数据目录')
    from .domain import data_dir, new_project
    root = data_dir()
    from .resource_location import require_resource_dir
    try:
        resources=require_resource_dir()
        for name in ['models', 'cache/features', 'recovery']:
            (resources / name).mkdir(parents=True, exist_ok=True)
    except (OSError,ValueError):
        # Leave the UI available so a missing removable drive can be reselected.
        pass
    # An actual write check reports a read-only data directory before work starts.
    with tempfile.TemporaryFile(dir=root) as probe:
        probe.write(b'GeoForma')
        probe.flush()
    check()
    progress(2, '读取应用配置')
    from .runtime_hardware import HardwareProbe
    hardware_probe=HardwareProbe()
    from .model_preferences import application_settings,last_model
    settings = application_settings()
    settings.sync()
    if settings.status() != QSettings.Status.NoError:
        raise OSError('无法读取应用配置，请检查当前用户的访问权限。')
    project = new_project(last_model(settings))  # Resolves weights without model loading.
    check()
    progress(3, '准备地理数据组件')
    from PIL import Image  # Initialize Pillow before Qt image rendering and raster workers.
    import rasterio
    # This also detects a missing bundled PROJ database, without opening source imagery.
    if rasterio.crs.CRS.from_epsg(3857).to_epsg() != 3857:
        raise RuntimeError('地理坐标组件未能初始化。')
    check()
    progress(4, '加载标注工作台')
    from .window import MainWindow  # Imports only; no widgets, Torch or model execution here.
    from .ui.panels import imagery,annotation,status  # Import classes on the worker; instantiate on the UI thread.
    from .ui import image_toolbar,label_table,raster_presenter,reference_switcher,visibility_button
    hardware=hardware_probe.result(check)
    check()
    return StartupContext(root, project, MainWindow, hardware)


class StartupWorker(QThread):
    progress = Signal(int, str)

    def __init__(self, prepare=prepare_startup, parent=None):
        super().__init__(parent)
        self.prepare = prepare
        self.result = None
        self.error = ''
        self.cancelled = False

    def check(self):
        if self.isInterruptionRequested():
            raise StartupCancelled()

    def run(self):
        try:
            self.result = self.prepare(self.progress.emit, self.check)
            self.check()
        except StartupCancelled:
            self.cancelled = True
        except Exception:
            self.error = traceback.format_exc()


class StartupSplash(QWidget):
    cancelRequested = Signal()
    retryRequested = Signal()

    def __init__(self):
        super().__init__(None, Qt.WindowType.SplashScreen | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle('GeoForma · 启动')
        self.setWindowIcon(application_icon())
        self.setFixedSize(610, 350)
        self.allow_close = False
        self.details = ''
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 22, 36, 28)
        top = QHBoxLayout()
        top.addStretch()
        self.exit_button = QPushButton('×')
        self.exit_button.setToolTip('关闭')
        self.exit_button.setFixedSize(28, 28)
        self.exit_button.setStyleSheet('QPushButton{background:transparent;color:#9db9c7;border:0;padding:0;font-size:21px;} QPushButton:hover{color:white;background:#274d5e;}')
        self.exit_button.clicked.connect(self.close)
        top.addWidget(self.exit_button)
        layout.addLayout(top)
        layout.addStretch(1)
        hero = QHBoxLayout()
        hero.setSpacing(24)
        mark = QLabel()
        mark.setPixmap(application_icon().pixmap(132, 132))
        mark.setFixedSize(132, 132)
        hero.addWidget(mark)
        names = QVBoxLayout()
        names.setSpacing(7)
        title = QLabel('GeoForma')
        title.setStyleSheet('color:#f0f9fb;font-family:"Segoe UI";font-size:38px;font-weight:600;background:transparent;')
        names.addWidget(title)
        caption = QLabel('遥感影像标注')
        caption.setStyleSheet('color:#afd0dc;font-size:14px;background:transparent;')
        names.addWidget(caption)
        version = QLabel('v' + VERSION)
        version.setStyleSheet('color:#91b0bf;font-size:11px;background:transparent;')
        names.addWidget(version)
        names.addStretch()
        hero.addLayout(names, 1)
        layout.addLayout(hero)
        layout.addStretch(2)
        self.status = QLabel('正在启动')
        self.status.setStyleSheet('color:#c7dfe7;font-size:12px;background:transparent;')
        layout.addWidget(self.status)
        self.progress = TaskProgressBar(variant='dark',expanding=True,smooth=True)
        layout.addWidget(self.progress)
        self.error_row = QWidget()
        row = QHBoxLayout(self.error_row)
        row.setContentsMargins(0, 0, 0, 0)
        self.retry = QPushButton('重试')
        self.detail_button = QPushButton('详细信息')
        self.retry.clicked.connect(self.retryRequested)
        self.detail_button.clicked.connect(self.show_details)
        row.addWidget(self.retry)
        row.addWidget(self.detail_button)
        row.addStretch()
        layout.addWidget(self.error_row)
        self.error_row.hide()

    @Slot(int, str)
    def set_phase(self, value, message):
        if self.progress.model.report(value,6,message):self.status.setText(f'启动软件 · {value}/6 · '+message)

    def show_failure(self, details):
        self.progress.model.finish('failed')
        self.details = details
        self.status.setText('启动未完成')
        self.status.setStyleSheet('color:#ffb7b7;font-size:12px;background:transparent;')
        self.error_row.show()

    def show_details(self):
        from .error_messages import user_message
        box = QMessageBox(QMessageBox.Icon.Warning, 'GeoForma', user_message(self.details), QMessageBox.StandardButton.Ok, self)
        box.setDetailedText(self.details)
        from .ui.modal import dialog_result
        dialog_result(box)

    def reset(self):
        self.details = ''
        self.error_row.hide()
        self.status.setStyleSheet('color:#c7dfe7;font-size:12px;background:transparent;')
        self.progress.model.begin('启动软件','startup',cancellable=True)
        self.set_phase(0, '正在启动')

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bounds = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        gradient = QLinearGradient(bounds.topLeft(), bounds.bottomRight())
        gradient.setColorAt(0, QColor('#102b3b'))
        gradient.setColorAt(1, QColor('#154751'))
        painter.setPen(QPen(QColor('#346172'), 1))
        painter.setBrush(gradient)
        painter.drawRoundedRect(bounds, 16, 16)
        draw_grid_pattern(painter, bounds.adjusted(7, 7, -7, -7), .26)

    def closeEvent(self, event):
        if self.allow_close:
            event.accept()
        else:
            event.ignore()
            self.cancelRequested.emit()


class StartupController(QObject):
    ready = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, app, project_path=None, recover_latest=False, *, prepare=prepare_startup, window_factory=None):
        super().__init__(app)
        self.app = app
        self.project_path = project_path
        self.recover_latest = recover_latest
        self.prepare = prepare
        self.window_factory = window_factory
        self.window = None
        self.worker = None
        self.stopping = False
        self.splash = StartupSplash()
        self.splash.cancelRequested.connect(self.cancel)
        self.splash.retryRequested.connect(self._begin)
        self.reveal_timer=QTimer(self);self.reveal_timer.setSingleShot(True);self.reveal_timer.setInterval(COMPLETION_HOLD_MS)
        self.reveal_timer.timeout.connect(self._reveal);self.splash.progress.completionPainted.connect(self._completed_frame)

    def start(self):
        self.app.setQuitOnLastWindowClosed(False)
        self.splash.show()
        screen = self.splash.screen()
        self.splash.move(screen.availableGeometry().center() - self.splash.rect().center())
        QTimer.singleShot(0, self._begin)

    @Slot()
    def _begin(self):
        if self.worker is not None or self.stopping:
            return
        self.splash.reset()
        self.reveal_timer.stop()
        self.worker = StartupWorker(self.prepare, self)
        worker=self.worker
        self.worker.progress.connect(lambda value,message:self.splash.set_phase(value,message) if self.worker is worker else None)
        self.worker.finished.connect(self._finished)
        self.worker.start()

    @Slot()
    def _finished(self):
        worker = self.worker
        self.worker = None
        if self.stopping or worker.cancelled:
            worker.deleteLater()
            self._exit()
            return
        context, error = worker.result, worker.error
        worker.deleteLater()
        if error:
            self._fail(error)
            return
        self.splash.set_phase(5, '准备界面')
        QTimer.singleShot(0, lambda: self._construct(context))

    def _construct(self, context):
        if self.stopping:
            self._exit()
            return
        try:
            # Always create widgets on the application thread, after the worker ends.
            factory = self.window_factory or (lambda ctx: ctx.window_type(self.project_path, recover_latest=self.recover_latest, startup_context=ctx))
            self.window = factory(context)
            self.splash.set_phase(6, '就绪')
            self.splash.progress.model.finish('complete','启动完成');self.splash.status.setText('启动完成')
        except Exception:
            self._fail(traceback.format_exc())

    def _completed_frame(self):
        if not self.stopping and self.window is not None:self.reveal_timer.start()

    def _reveal(self):
        if self.stopping:return
        self.window.show()
        self.splash.allow_close = True
        self.splash.close()
        self.app.setQuitOnLastWindowClosed(True)
        self.ready.emit(self.window)

    def _fail(self, details):
        self.reveal_timer.stop()
        try:
            from .resource_location import require_resource_dir
            from .logging_limits import append_error
            append_error(require_resource_dir(),details)
        except (OSError,ValueError,RuntimeError):
            pass
        self.splash.show_failure(details)
        self.failed.emit(details)

    @Slot()
    def cancel(self):
        self.stopping = True
        self.splash.progress.model.request_cancel('正在退出');self.splash.status.setText('启动软件 · 正在退出')
        self.splash.error_row.hide()
        if self.worker is not None:
            self.worker.requestInterruption()
        else:
            self._exit()

    def _exit(self):
        self.reveal_timer.stop()
        if self.window is not None:self.window.close()
        self.splash.progress.model.finish('cancelled','已停止启动')
        self.splash.allow_close = True
        self.splash.close()
        self.cancelled.emit()
        self.app.quit()
