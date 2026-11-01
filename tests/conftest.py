"""Keep application preferences isolated from user configuration and other tests."""
import pytest


@pytest.fixture(autouse=True)
def isolated_application_preferences(tmp_path,monkeypatch):
    monkeypatch.setenv('GEOFORMA_SETTINGS_FILE',str(tmp_path/'application.ini'))
    monkeypatch.setenv('GEOFORMA_DATA_DIR',str(tmp_path/'app-data'))
    # A developer's downloaded weights must not leak into isolated unit tests.
    import geoforma.distribution as distribution
    original=distribution.bundled_checkpoint
    def no_bundled_checkpoint(name):return None
    no_bundled_checkpoint.__wrapped__=original
    monkeypatch.setattr(distribution,'bundled_checkpoint',no_bundled_checkpoint)


@pytest.fixture
def hover_move():
    """The offscreen plugin can omit enter/leave events at high pixel ratios."""
    from PySide6.QtCore import Qt,QEvent,QPointF
    from PySide6.QtGui import QEnterEvent,QMouseEvent
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from shiboken6 import isValid
    previous=None
    def move(widget,position=None):
        nonlocal previous
        app=QApplication.instance();position=widget.rect().center() if position is None else position
        QTest.mouseMove(widget,position);app.processEvents()
        if app.platformName()=='offscreen' and widget.devicePixelRatioF()>1:
            if previous is not None and isValid(previous):app.sendEvent(previous,QEvent(QEvent.Type.Leave))
            global_pos=QPointF(widget.mapToGlobal(position))
            app.sendEvent(widget,QEnterEvent(QPointF(position),QPointF(widget.mapTo(widget.window(),position)),global_pos))
            app.sendEvent(widget,QMouseEvent(QEvent.Type.MouseMove,QPointF(position),global_pos,
                Qt.MouseButton.NoButton,Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier))
        previous=widget;app.processEvents()
    yield move
    if previous is not None and isValid(previous):QApplication.sendEvent(previous,QEvent(QEvent.Type.Leave))
