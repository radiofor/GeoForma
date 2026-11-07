"""Persistent results, accurate terminal states, and a shared visual center."""
import threading,time
from PySide6.QtCore import QPoint
from PySide6.QtTest import QTest
from test_workbench import workbench,fake_image


def until(app,predicate):
    deadline=time.monotonic()+4
    while not predicate():
        app.processEvents();QTest.qWait(2);assert time.monotonic()<deadline


def test_terminal_meter_clears_without_hiding_frame_and_new_task_is_safe(workbench,monkeypatch):
    w,app,wait,errors=workbench
    monkeypatch.setattr(w.pool,'start',lambda task:None)
    w.run('导出标签',lambda task:None,lambda _:None,kind='export');w.task.run()
    assert w.progress.phase=='complete' and w.progress.isVisible()
    w.progress_presentation.clear_terminal()
    assert w.progress_panel.isVisible() and not w.progress.isVisible()
    w.run('导入影像',lambda task:None,lambda _:None,kind='import')
    w.progress_presentation.clear_terminal()
    assert w.progress.phase=='running' and w.progress.isVisible()
    w.task.run();assert not errors


def test_preparation_completion_uses_prepared_file_not_current_image(workbench):
    w,app,wait,errors=workbench
    current=fake_image('one','current.tif');next_image=fake_image('two','next.tif')
    w.image=current;w.project['images']=[current,next_image]
    w.progress_presentation.begin('preparation','准备影像 · next.tif')
    w.progress_presentation.finish('准备影像 · next.tif','complete')
    assert w.statusBar().currentMessage()=='影像预处理完成 · next.tif'
    assert not errors


def test_preparation_all_complete_requires_every_current_signature(workbench):
    from geoforma.workflow import preparation_signature
    w,app,wait,errors=workbench
    images=[fake_image('one','one.tif'),fake_image('two','two.tif')]
    w.project['images']=images;w.image=images[0]
    for image in images:
        image['ready']=True;image['prepared_full_signature']=preparation_signature(image,w.project['model'])
    w.progress_presentation.begin('preparation','准备影像 · two.tif')
    w.progress_presentation.finish('准备影像 · two.tif','complete')
    assert w.statusBar().currentMessage()=='全部影像预处理完成 · 共 2 幅'
    images[0]['prepared_full_signature']='stale'
    w.progress_presentation.begin('preparation','准备影像 · two.tif')
    w.progress_presentation.finish('准备影像 · two.tif','complete')
    assert w.statusBar().currentMessage()=='影像预处理完成 · two.tif'
    assert not errors


def test_completed_meter_stays_visible_and_next_task_replaces_it(workbench):
    w,app,wait,errors=workbench;release=threading.Event()
    def work(task):
        task.signals.progress.emit(0,0,'读取数据…');assert release.wait(5)
    assert not w.progress.isVisible() and w.progress.phase=='idle'
    assert w.state_label.text()=='未导入影像' and w.task_text.text()=='导入影像以开始标注'
    assert not hasattr(w,"progress_count")
    def positions():
        return [(control.mapTo(w.statusBar(),QPoint()).toTuple(),control.size().toTuple())
                for control in (w.progress,w.progress_action)]
    try:
        w.run('导入影像 A',work,lambda _:None,kind='import')
        until(app,lambda:w.progress.timer.isActive())
        anchors=positions();assert not hasattr(w,"progress_count")
    finally:release.set()
    wait();assert w.progress.phase=='complete' and not w.progress.timer.isActive()
    assert w.progress.isVisible() and w.progress.value()==100
    assert '影像导入完成' in w.statusBar().currentMessage()
    assert not hasattr(w,"progress_count")
    assert positions()==anchors
    assert '导入影像 A' in w.progress_panel.toolTip()
    for _ in range(3):w.update_controls();app.processEvents()
    assert w.progress.phase=='complete' and 'A' in w.task_text.text() and '读取数据' in w.task_text.text()
    release.clear()
    try:
        w.run('导出标签 B',work,lambda _:None,kind='export')
        until(app,lambda:w.task_stage=='读取数据…')
        assert w.progress.phase=='running' and w.cancel_button.isVisible()
        assert positions()==anchors
        assert '导入影像 A' not in w.task_text.text()
    finally:release.set()
    wait();assert w.progress.phase=='complete' and '导出标签 B' in w.progress_panel.toolTip() and not errors


def test_failed_and_cancelled_tasks_never_show_a_completed_meter(workbench):
    w,app,wait,errors=workbench
    def failing(task):
        task.signals.progress.emit(3,10,'写入标签…');raise ValueError('无法写入')
    w.run('导出',failing,lambda _:None,kind='export');wait()
    assert errors and w.progress.phase=='failed' and w.progress.value()==30
    assert w.progress.phase=='failed' and not w.progress.timer.isActive()
    release=threading.Event()
    def cancellable(task):
        task.signals.progress.emit(2,10,'读取影像…');assert release.wait(5);task.check()
    try:
        w.run('导入',cancellable,lambda _:None,kind='import')
        until(app,lambda:w.progress.value()==2)
        w.cancel()
    finally:release.set()
    wait();assert w.progress.phase=='cancelled' and w.progress.value()==20
    assert '已取消' in w.statusBar().currentMessage() and w.progress.isVisible()


def test_every_status_element_shares_a_vertical_center_at_all_window_widths(workbench):
    w,app,wait,errors=workbench
    controls=(w.state_label,w.task_text,w.progress_percent,w.progress,w.background_button,w.context_status)
    for width in (1024,1440,3440):
        w.resize(width,800);w.background_activity.delay=0
        w.background_activity.set('autosave','自动保存','当前项目');app.processEvents();app.processEvents()
        centers=[control.mapTo(w.statusBar(),QPoint(0,0)).y()+control.height()/2 for control in controls if control.isVisible()]
        assert max(centers)-min(centers)<=1
        assert all(abs(center-w.statusBar().height()/2)<=1 for center in centers)
        for label in (w.state_label,w.task_text,w.progress_percent,w.edit_status):
            assert label.contentsRect().height()>=label.fontMetrics().height()
        w.background_activity.set('autosave','');app.processEvents()
    assert not errors


def test_new_task_clears_previous_notice_and_terminal_text_is_not_repeated(workbench,monkeypatch):
    w,app,wait,errors=workbench
    monkeypatch.setattr(w.pool,'start',lambda task:None)
    w.statusBar().showMessage('上一项导入结果',8000)
    w.run('导入影像',lambda task:None,lambda _:None,kind='import')
    assert w.statusBar().currentMessage()=='' and not w.statusBar().message_timer.isActive()
    w.task_progress(12,12,'lake.tif');w.task.run()
    assert w.state_label.text()=='导入影像' and w.progress_count_text=='影像 12 / 12'
    assert w.progress.phase=='complete' and w.task_text.text()=='lake.tif'
    assert '影像导入完成' in w.statusBar().currentMessage()
    w.run('下一项任务',lambda task:None,lambda _:None,kind='export');w.cancel();w.task.run()
    assert w.progress.phase=='cancelled' and '已取消' in w.statusBar().currentMessage()
    assert not errors


def test_unknown_total_completion_does_not_repeat_the_result(workbench,monkeypatch):
    w,app,wait,errors=workbench
    monkeypatch.setattr(w.pool,'start',lambda task:None)
    w.run('加载模型',lambda task:None,lambda _:None,kind='model');w.task.run()
    assert w.state_label.text()=='加载模型' and w.progress.phase=='complete'
    assert w.task_text.text().startswith('SAM')
    assert not errors


def test_cancelled_unknown_total_keeps_the_task_name(workbench,monkeypatch):
    w,app,wait,errors=workbench
    monkeypatch.setattr(w.pool,'start',lambda task:None)
    w.run('导出标签',lambda task:None,lambda _:None,kind='export')
    w.cancel();w.task.run()
    assert w.state_label.text()=='导出标签' and w.progress.phase=='cancelled'
    assert not errors


def test_idle_with_image_and_background_activity_is_unambiguous(workbench):
    w,app,wait,errors=workbench
    w.image=fake_image('one','lake.tif');w.image['ready']=True;w.project['images']=[w.image]
    w.update_controls();assert w.state_label.text()=='就绪'
    assert w.task_text.text()=='当前影像 · lake.tif' and not w.progress.isVisible()
    w.background_activity.delay=0;w.background_activity.set('autosave','自动保存','项目 A')
    app.processEvents();app.processEvents()
    assert w.task_text.text()=='当前影像 · lake.tif' and w.background_button.isVisible()
    w.statusBar().showMessage('已保存',1000)
    assert w.statusBar().text_slot.currentIndex()==1
    w.background_activity.set('autosave','')


def test_notice_waits_until_foreground_task_finishes(workbench,monkeypatch):
    w,app,wait,errors=workbench
    monkeypatch.setattr(w.pool,'start',lambda task:None)
    w.run('导入影像',lambda task:None,lambda _:None,kind='import')
    bar=w.statusBar();bar.showMessage('导入结果',30)
    QTest.qWait(60);app.processEvents()
    assert bar.currentMessage()=='导入结果' and bar.text_slot.currentIndex()==0
    w.task.run();assert bar.text_slot.currentIndex()==1
    QTest.qWait(60);app.processEvents();assert bar.currentMessage()==''
