"""应用窗口的尺寸与显示状态，独立于项目和工作恢复。"""
from PySide6.QtCore import QByteArray, QSize, Qt


DEFAULT_WINDOW_SIZE = QSize(1440, 900)
LEFT_SIDEBAR_WIDTHS = (280, 400)
RIGHT_SIDEBAR_WIDTHS = (320, 480)
DEFAULT_SIDEBAR_WIDTHS = (288, 320)
_STATES = {"normal": Qt.WindowState.WindowNoState,
           "maximized": Qt.WindowState.WindowMaximized,
           "fullscreen": Qt.WindowState.WindowFullScreen}


def restore_window(window, settings):
    window.resize(DEFAULT_WINDOW_SIZE)
    geometry = settings.value("window/geometry")
    if isinstance(geometry, (QByteArray, bytes, bytearray)):
        # Qt 同时恢复普通窗口尺寸，并处理屏幕移除、分辨率和工作区变化。
        window.restoreGeometry(QByteArray(geometry))
    state = settings.value("window/display_state", "normal", type=str)
    window.setWindowState(_STATES.get(state, Qt.WindowState.WindowNoState))
    raw=settings.value('window/sidebar_widths',[]);widths=DEFAULT_SIDEBAR_WIDTHS
    if isinstance(raw,(list,tuple)) and len(raw)==2:
        try:widths=[max(low,min(high,int(value))) for value,(low,high) in zip(raw,(LEFT_SIDEBAR_WIDTHS,RIGHT_SIDEBAR_WIDTHS))]
        except (TypeError,ValueError,OverflowError):pass
    window.resizeDocks([window.image_dock,window.annotation_dock],widths,Qt.Orientation.Horizontal)


def remember_window(window, settings):
    # saveGeometry 包含最大化/全屏之前的普通窗口大小，不用屏幕大小覆盖它。
    settings.setValue("window/geometry", window.saveGeometry())
    state = "fullscreen" if window.isFullScreen() else "maximized" if window.isMaximized() else "normal"
    settings.setValue("window/display_state", state)
    settings.setValue('window/sidebar_widths',[window.image_dock.width(),window.annotation_dock.width()])
    settings.sync()
