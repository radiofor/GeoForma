"""Task names survive generic worker stages and progress totals change units."""
import threading,time
import pytest
from PySide6.QtTest import QTest
from test_workbench import workbench,fake_image


def test_worker_stages_keep_distinct_task_identity_and_object(workbench):
    w,app,wait,errors=workbench
    w.image=fake_image('one','lake.tif');w.project['images']=[w.image]
    cases=[('import','导入影像'),('reference_import','导入参考'),('model','加载模型'),
           ('model_warmup','加载模型'),('preparation','准备影像'),('interactive','逐个分割'),
           ('reshape','重塑轮廓'),('bands','调整波段'),('export','导出标签')]
    for kind,name in cases:
        release=threading.Event()
        def work(task):
            task.signals.progress.emit(0,0,'读取数据…')
            assert release.wait(5)
        try:
            assert w.run('导入 NDWI 参考影像' if kind=='reference_import' else name,work,lambda _:None,kind=kind)
            deadline=time.monotonic()+3
            while w.task_stage!='读取数据…':
                app.processEvents();QTest.qWait(2);assert time.monotonic()<deadline
            assert w.state_label.text()==('影像预处理' if kind=='preparation' else name)
            assert w.task_text.text().startswith('读取数据')
            assert name not in w.task_text.text()
            if kind in ('model','model_warmup'):assert 'SAM' in w.task_text.text()
            if kind=='reference_import':assert 'NDWI' in w.task_text.text()
            if kind in ('interactive','reshape','bands','export'):assert 'lake.tif' in w.task_text.text()
            w.statusBar().showMessage('一条临时提示',10)
            assert w.state_label.text()==('影像预处理' if kind=='preparation' else name) and w.progress.isVisible()
            if kind in ('model','model_warmup'):
                w.task_progress(0,0,'加载 SAM 模型…')
                assert w.task_text.text()==w.task_title.partition('：')[2]
                w.task_progress(0,0,'加载模型…')
                assert w.task_text.text()==w.task_title.partition('：')[2]
                w.task_progress(0,0,'加载模型权重…')
                assert w.task_text.text()=='读取模型权重 · '+w.task_title.partition('：')[2]
        finally:release.set()
        wait()
        assert not w.task_title and not w.task_stage and w.progress.isVisible()
        assert w.progress.phase=='complete'
        assert w.state_label.text()==('影像预处理' if kind=='preparation' else name)
    assert not errors


def test_preparation_download_progress_is_not_mislabeled_as_image_blocks(workbench):
    w,app,wait,errors=workbench
    w.task_kind='preparation';w.task_title='准备影像：lake.tif';w.progress_image_order=(2,24)
    w.task_progress(37,100,'下载模型权重…')
    assert w.progress_count_text=='影像 2/24' and w.progress_percent.text()=='37%'
    assert w.task_text.text().startswith('下载模型权重 · SAM') and '影像：lake.tif' in w.task_text.text()
    w.task_progress(0,0,'加载 SAM 模型…')
    assert w.progress_count_text=='影像 2/24'
    assert w.task_text.text().startswith('SAM') and '影像：lake.tif' in w.task_text.text()
    w.task_progress(3,9,'准备影像 3/9')
    assert w.progress_count_text=='影像 2/24 · 块 3 / 9'
    w.task_kind=None


def test_late_callbacks_cannot_finish_or_mutate_a_new_task(workbench,monkeypatch):
    w,app,wait,errors=workbench;queued=[];values=[]
    monkeypatch.setattr(w.pool,'start',queued.append)
    w.run('First',lambda task:1,values.append,kind='import');old=w.task
    old.run();assert values==[1] and w.task is None
    w.run('Second',lambda task:2,values.append,kind='import');current=w.task
    old.signals.progress.emit(1,10,'stale progress')
    old.signals.result.emit(999);old.signals.error.emit('stale failure');old.signals.finished.emit()
    assert w.task is current and values==[1] and not errors
    assert w.progress.model.state.title=='Second' and w.progress.model.state.phase=='running'
    w.cancel();current.run()
    assert values==[1] and w.task is None and w.progress.model.state.phase=='cancelled'


def test_cancelled_task_cannot_publish_a_partial_result(workbench,monkeypatch):
    w,app,wait,errors=workbench;values=[]
    monkeypatch.setattr(w.pool,'start',lambda task:None)
    partial={'cancelled':True,'labels':[{'id':'completed'}]}
    w.run('更新轮廓',lambda task:partial,values.append,kind='interactive');task=w.task
    w.cancel();task.run()
    assert not values and w.progress.model.state.phase=='cancelled' and not errors


def test_completion_hook_failure_never_publishes_success(workbench,monkeypatch):
    w,app,wait,errors=workbench;states=[]
    monkeypatch.setattr(w.pool,'start',lambda task:None)
    w.progress.model.changed.connect(lambda state:states.append(state.phase))
    def fail_commit():raise ValueError('提交结果失败')
    assert w.run('导出标签',lambda task:None,lambda _:None,kind='export',on_finished=fail_commit)
    w.task.run()
    assert errors and '提交结果失败' in errors[-1]
    assert w.progress.phase=='failed' and 'complete' not in states
    assert '完成' not in w.statusBar().currentMessage()


def test_completion_hook_starting_new_task_preserves_its_progress(workbench,monkeypatch):
    w,app,wait,errors=workbench;queued=[]
    monkeypatch.setattr(w.pool,'start',queued.append)
    def start_next():
        assert w.run('下一项',lambda task:None,lambda _:None,kind='export')
    assert w.run('第一项',lambda task:None,lambda _:None,kind='import',on_finished=start_next)
    first=w.task;first.run()
    assert w.task is not None and w.task is not first
    assert w.progress.phase=='running' and w.progress.model.state.title=='下一项'
    w.task.run();assert w.progress.phase=='complete' and not errors


def test_task_error_is_non_modal_and_keeps_diagnostics_in_log(workbench,monkeypatch):
    from geoforma.controllers.tasks import TaskWorkflow
    from PySide6.QtWidgets import QMessageBox
    w,app,wait,errors=workbench
    monkeypatch.setattr(QMessageBox,'exec',lambda *args:pytest.fail('错误提示不得阻塞'))
    TaskWorkflow.error(w,'Traceback details\nValueError: 影像读取失败')
    assert w.last_error=='影像读取失败' and 'Traceback details' in w.log.toPlainText()
    toast=w.statusBar()._error_toast
    assert toast.label.text()=='影像读取失败' and toast.label.isVisible()
    assert toast.timer.interval()==2000
