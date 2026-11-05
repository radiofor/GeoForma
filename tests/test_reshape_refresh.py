"""Unchanged controls stay unchanged; right-click commits one UI transaction."""
import copy,time
from PySide6.QtCore import QObject,QEvent,Qt
from PySide6.QtTest import QTest
from shapely.geometry import shape
from test_reshape import workbench,raster_image
from test_reshape_crossings import STROKE,EXPECTED


class Watch(QObject):
    def __init__(self,widgets):
        super().__init__();self.events=[];self.paints=[]
        for widget in widgets:widget.installEventFilter(self)
    def eventFilter(self,widget,event):
        if event.type()==QEvent.Type.EnabledChange:self.events.append(widget)
        if event.type()==QEvent.Type.Paint:self.paints.append(widget)
        return False


def settle(app):
    for _ in range(5):app.processEvents()


def test_repeated_control_refresh_does_not_toggle_locked_widgets(workbench):
    w,app,tmp=workbench;w.show();settle(app);w.begin_reshape();settle(app)
    widgets=[w.images,w.import_button,w.model_button,w.single_polygon,w.auto_apply,w.apply_button]
    watch=Watch(widgets)
    for _ in range(12):w.update_controls();settle(app)
    assert not watch.events
    assert not watch.paints
    assert all(not widget.isEnabled() for widget in widgets)


def test_right_click_accepts_repeated_crossings_with_one_label_refresh(workbench,monkeypatch):
    w,app,tmp=workbench;w.show();settle(app);w.view.fit_image();w.begin_reshape()
    for point in STROKE:w.add_reshape_point(*point)
    before=copy.deepcopy(w.project['labels']);calls=[];refresh=w.refresh_labels
    def counted():calls.append(1);refresh()
    monkeypatch.setattr(w,'refresh_labels',counted)
    QTest.mouseClick(w.view.viewport(),Qt.MouseButton.RightButton)
    deadline=time.monotonic()+5
    while w.task:app.processEvents();time.sleep(.002);assert time.monotonic()<deadline
    settle(app)
    assert calls==[1] and w.reshape_session is None and not w.view.reshape_items
    assert not w.draft and shape(w.project['labels'][0]['geometry']).equals(EXPECTED)
    assert w.project['labels'][0]['editing_state']=='manual'
    w.undo_context();assert w.project['labels']==before
