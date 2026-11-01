import threading,time
from PySide6.QtCore import QPoint
from PySide6.QtTest import QTest
from test_workbench import workbench,fake_image


def test_preparation_displays_image_order_and_block_order_before_progress_bar(workbench):
    w,app,wait,errors=workbench;release=threading.Event()
    w.project['images']=[fake_image('a'),fake_image('b','two.tif')]
    w.refresh_images();w.images.setCurrentRow(0)
    def prepare(image,config,bounds,task):
        task.signals.progress.emit(3,9,'准备影像 3/9')
        assert release.wait(5)
        return {'count':9,'hits':0,'device':'cpu','checkpoint':config['checkpoint']}
    w.service.preprocess=prepare
    try:
        w.start_preparation(w.project['images'][1])
        deadline=time.monotonic()+3
        while w.progress_count.text()!='影像 2/2 · 块 3 / 9':
            app.processEvents();QTest.qWait(2);assert time.monotonic()<deadline
        assert w.progress_count.isVisible()
        assert w.state_label.parentWidget() is w.progress_panel
        assert w.progress_count.mapTo(w,QPoint()).x()<w.progress.mapTo(w,QPoint()).x()
        rect=w.progress_count.geometry()
        w.task_progress(9,9,'整理缓存');app.processEvents()
        assert w.progress_count.text()=='影像 2/2 · 100%' and w.progress_count.geometry()==rect
        w.task_progress(0,0,'加载 SAM 模型…');app.processEvents()
        assert w.state_label.text()=='准备影像' and '加载模型' in w.task_text.text() and 'SAM' in w.task_text.text() and 'two.tif' in w.task_text.text() and w.progress_count.geometry()==rect
        w.task_progress(9,9,'准备影像 9/9')
    finally:release.set()
    wait()
    assert w.progress_count.isVisible() and w.progress_count.text()=='影像 2/2 · 块 9 / 9' and not errors
    assert w.progress.phase=='complete' and w.progress.value()==100


def test_counter_handles_unknown_total_and_new_stage_without_stale_image_order(workbench):
    w,app,wait,errors=workbench
    w.update_progress_count(0,0);assert not w.progress_count.text()
    w.update_progress_count(0,12);assert w.progress_count.text()=='0%'
    w.update_progress_count(7,12);assert w.progress_count.text()=='58%'
    w.update_progress_count(99,12);assert w.progress_count.text()=='100%'


def test_units_follow_operation_and_stage(workbench):
    w,app,wait,errors=workbench
    for kind,stage,expected in (
        ('import','a.tif','影像 2 / 5'),
        ('reference_import','a.tif','参考 2 / 5'),
        ('export','导出 GPKG…','标签 2 / 5'),
        ('export','导出原始网格标签…','40%'),
        ('resource_install','复制资源','40%'),
        ('preparation','准备影像 2/5','块 2 / 5'),
        ('preparation','校验运行库','40%'),
    ):
        w.task_kind=kind;w.task_stage=stage;w.update_progress_count(2,5)
        assert w.progress_count.text()==expected
    w.task_kind=None;w.task_stage=''
