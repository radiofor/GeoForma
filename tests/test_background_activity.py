"""Concurrent workers keep their own status and never borrow the main cancel."""
import threading,time
import numpy as np
from PySide6.QtTest import QTest
from test_workbench import workbench,fake_image


def until(app,predicate):
    deadline=time.monotonic()+4
    while not predicate():
        app.processEvents();QTest.qWait(2);assert time.monotonic()<deadline


def test_actual_raster_and_model_workers_keep_separate_status_and_cancel(workbench):
    w,app,wait,errors=workbench;model_done=threading.Event();raster_done=threading.Event()
    im=fake_image('one','lake.tif');im['display_recipe']={'bands':[1,2,3],'ranges':[[0,255]]*3}
    w.image=im;w.project['images']=[im];w.view.set_image(2000,2000)
    w.background_activity.delay=10
    def model(task):
        task.signals.progress.emit(0,0,'加载模型权重…');assert model_done.wait(5)
    def reader(*args):
        assert raster_done.wait(5)
        return np.zeros((4,4,3),dtype=np.uint8),np.ones((4,4),dtype=bool)
    w.raster_renderer.reader=reader
    try:
        w.run('模型加载',model,lambda _:None,kind='model')
        w.raster_renderer.request(im,w.render_generation,[0,0,2000,2000],1400,True)
        raster_task=w.raster_renderer.task
        until(app,lambda:'raster' in w.background_activity.visible and w.task_stage=='加载模型权重…')
        assert w.state_label.text()=='加载模型'
        assert '显示主影像' in w.background_button.toolTip() and 'lake.tif' in w.background_button.toolTip()
        w.statusBar().showMessage('工作已自动保存',2000)
        assert w.statusBar().text_slot.currentIndex()==0 and '读取模型权重' in w.task_text.text()
        w.cancel();assert w.task.cancel_event.is_set() and not raster_task.cancel_event.is_set()
        model_done.set();until(app,lambda:w.task is None)
        assert w.state_label.text()=='加载模型' and 'SAM' in w.task_text.text()
        assert not w.task_text.text().startswith('显示主影像')
        assert not w.cancel_button.isVisible() and w.progress.isVisible()
        assert w.progress.phase=='cancelled'
    finally:model_done.set();raster_done.set()
    wait()
    assert not w.background_activity.visible and not w.background_button.text() and not errors
    assert w.state_label.text()!='后台处理'


def test_background_registry_keeps_all_entries_and_ignores_short_or_stale_tasks(workbench):
    w,app,wait,errors=workbench;status=w.background_activity;status.delay=15
    status.set('raster','显示 NDWI 参考','old.tif');status.set('raster','')
    status.set('raster','显示 NDVI 参考','new.tif')
    status.set('autosave','自动保存','项目 A')
    status.set('smoothing','平滑标签')
    status.set('labels','准备标签','200 个目标')
    until(app,lambda:len(status.visible)==4)
    assert len(w.background_button.menu().actions())==4
    tooltip=w.background_button.toolTip()
    assert 'NDVI' in tooltip and 'old.tif' not in tooltip and '200 个目标' in tooltip and '自动保存' in tooltip
    for key in ('raster','smoothing','autosave','labels'):status.set(key,'')
    assert not w.background_button.text()
    status.set('autosave','自动保存');status.set('autosave','')
    QTest.qWait(30);app.processEvents()
    assert not status.visible and not w.background_button.text()
