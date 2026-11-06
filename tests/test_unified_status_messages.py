"""The one status message area remains readable at different lengths."""
from PySide6.QtCore import QEvent,QObject,QPoint,QPointF,Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from test_workbench import workbench


def settle(app):
    for _ in range(8):app.processEvents();QTest.qWait(1)


def test_status_message_priority_and_no_persistent_model_name(workbench):
    w,app,_,_=workbench;w.show();settle(app);bar=w.statusBar()
    w.context_status.setText('当前编辑状态');settle(app)
    assert bar.text_slot.currentWidget() is w.context_status
    assert not w.task_text.isVisible() and not bar.notice.isVisible()
    bar.showMessage('操作完成');settle(app)
    assert bar.text_slot.currentWidget() is bar.notice
    w.task_text.setText('SAM 模型加载中');bar.set_task_active(True);settle(app)
    assert bar.text_slot.currentWidget() is w.task_text
    bar.set_task_active(False);settle(app)
    assert bar.text_slot.currentWidget() is bar.notice
    bar.clearMessage();settle(app)
    assert bar.text_slot.currentWidget() is w.context_status and not w.task_text.isVisible()


def test_message_slot_fills_available_width_and_idle_context_is_empty(workbench):
    w,app,_,_=workbench;w.resize(1024,700);w.show();settle(app);bar=w.statusBar()
    w.update_draft_info();settle(app)
    assert not w.context_status.text()
    bar.showMessage('信息');settle(app)
    row=bar.content.layout();right=row.contentsMargins().right()
    assert bar.text_slot.geometry().right()==bar.content.width()-right-1
    w.background_activity.delay=0;w.background_activity.set('raster','显示影像');settle(app)
    assert w.background_button.isVisible()
    assert bar.text_slot.geometry().right()<w.background_button.geometry().left()
    w.background_activity.set('raster','');settle(app)
    assert bar.text_slot.geometry().right()==bar.content.width()-right-1


def test_long_status_message_wraps_and_is_scrollable_in_status_bar(workbench):
    w,app,_,_=workbench;w.resize(1024,700);w.show();settle(app);bar=w.statusBar()
    text='这是需要完整查看的状态信息。'*180
    bar.showMessage(text);settle(app);bar.notice.grab();settle(app)
    detail=bar.notice
    assert bar.text_slot.currentWidget() is detail and detail.text()==text
    assert detail.line_count()>4 and bar.height()>42
    assert detail.scrollbar.isVisible() and detail.scrollbar.maximum()>0
    pos=QPoint(40,10)
    wheel=QWheelEvent(QPointF(pos),QPointF(detail.mapToGlobal(pos)),QPoint(),QPoint(0,-120),
                      Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier,Qt.ScrollPhase.NoScrollPhase,False)
    QApplication.sendEvent(detail,wheel);assert detail.scrollbar.value()>0
    detail.scrollbar.setValue(detail.scrollbar.maximum());settle(app)
    assert detail.scrollbar.value()==detail.scrollbar.maximum()
    layout=detail._text_layout(detail.width()-47);last=layout.lineAt(layout.lineCount()-1)
    assert last.textStart()+last.textLength()==len(text)
    first=layout.lineAt(detail.scrollbar.value())
    assert last.y()+last.height()-first.y()<=detail.height()-6
    bar.clearMessage();settle(app)
    assert bar.text_slot.currentWidget() is w.context_status and bar.height()==42


def test_explicit_newlines_fit_without_unnecessary_scrollbar(workbench):
    w,app,_,_=workbench;w.resize(1024,700);w.show();settle(app);bar=w.statusBar()
    bar.showMessage('第一行\n第二行');settle(app)
    assert bar.notice.line_count()==2 and bar.height()>42
    assert bar.notice.scrollbar.maximum()==0 and bar.notice.scrollbar.isHidden()


def test_long_notice_pauses_timeout_while_reading_without_layout_churn(workbench):
    w,app,_,_=workbench;w.resize(1024,700);w.show();settle(app);bar=w.statusBar()
    text='很长的状态信息需要完整阅读。'*120
    bar.showMessage(text,500);settle(app);detail=bar.notice
    assert detail.scrollbar.maximum()>0 and bar.message_timer.isActive()
    detail.hoverChanged.emit(True);assert not bar.message_timer.isActive()
    class Watch(QObject):
        def __init__(self):super().__init__();self.events=[]
        def eventFilter(self,obj,event):
            if event.type() in (QEvent.Type.Show,QEvent.Type.Hide,QEvent.Type.Resize,QEvent.Type.Move):self.events.append(event.type())
            return False
    watch=Watch();detail.scrollbar.installEventFilter(watch)
    for _ in range(4):detail.grab();settle(app)
    QTest.qWait(550);settle(app)
    assert bar.currentMessage()==text and not watch.events
    detail.hoverChanged.emit(False);QTest.qWait(550);settle(app)
    assert not bar.currentMessage()
