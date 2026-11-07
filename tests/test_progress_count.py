import threading,time
from PySide6.QtCore import QPoint
from PySide6.QtTest import QTest
from test_workbench import workbench,fake_image


def test_preparation_displays_one_message_with_image_and_block_order(workbench):
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
        while w.progress_count_text!='影像 2/2 · 块 3 / 9':
            app.processEvents();QTest.qWait(2);assert time.monotonic()<deadline
        assert w.state_label.isVisible()
        assert w.state_label.parentWidget() is w.progress_panel
        assert w.state_label.text()=='影像预处理' and w.progress_percent.text()=='33%'
        assert '影像 2/2 · 块 3 / 9' in w.task_text.text() and 'two.tif' in w.task_text.text()
        positions=[widget.mapTo(w,QPoint()).x() for widget in (w.state_label,w.progress_percent,w.progress)]
        assert positions==sorted(positions) and w.progress_percent.width()==44
        w.task_progress(9,9,'整理缓存');app.processEvents()
        assert w.progress_count_text=='影像 2/2' and w.progress_percent.text()=='100%'
        w.task_progress(0,0,'加载 SAM 模型…');app.processEvents()
        assert w.state_label.text()=='加载模型' and 'SAM' in w.task_text.text() and 'two.tif' in w.task_text.text() and '影像 2/2' in w.task_text.text()
        assert w.progress_percent.text()=='--%'
        assert [widget.mapTo(w,QPoint()).x() for widget in (w.state_label,w.progress_percent,w.progress)]==positions
        w.task_progress(8,9,'检查完整影像缓存');app.processEvents()
        assert w.state_label.text()=='检查影像缓存' and w.progress_percent.text()=='88%'
        w.task_progress(1,9,'准备影像 1/9');app.processEvents()
        assert w.state_label.text()=='影像预处理' and w.progress_percent.text()=='11%'
        assert [widget.mapTo(w,QPoint()).x() for widget in (w.state_label,w.progress_percent,w.progress)]==positions
        w.task_progress(9,9,'准备影像 9/9')
    finally:release.set()
    wait()
    assert w.progress_count_text=='影像 2/2 · 块 9 / 9' and not errors
    assert w.progress.phase=='complete' and w.progress.value()==100


def test_counter_handles_unknown_total_and_new_stage_without_stale_image_order(workbench):
    w,app,wait,errors=workbench
    w.update_progress_count(0,0);assert not w.progress_count_text
    w.update_progress_count(0,12);assert w.progress_percent.text()=='0%'
    w.update_progress_count(7,12);assert w.progress_percent.text()=='58%'
    w.update_progress_count(99,12);assert w.progress_percent.text()=='100%'


def test_units_follow_operation_and_stage(workbench):
    w,app,wait,errors=workbench
    for kind,stage,expected in (
        ('import','a.tif','影像 2 / 5'),
        ('reference_import','a.tif','参考 2 / 5'),
        ('export','导出 GPKG…','标签 2 / 5'),
        ('export','导出原始网格标签…',''),
        ('resource_install','复制资源',''),
        ('preparation','准备影像 2/5','块 2 / 5'),
        ('preparation','校验运行库',''),
    ):
        w.task_kind=kind;w.task_stage=stage;w.update_progress_count(2,5)
        assert w.progress_count_text==expected
    w.task_kind=None;w.task_stage=''
