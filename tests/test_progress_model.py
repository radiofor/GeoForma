"""Shared lifecycle guarantees, independent owners, retries and renderer behavior."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from geoforma.progress import ProgressModel
from geoforma.ui.progress_bar import TaskProgressBar


@pytest.mark.parametrize('outcome',['complete','cancelled','failed'])
def test_terminal_result_is_retained_and_rejects_late_reports(outcome):
    model=ProgressModel();token=model.begin('湖泊标签','export',cancellable=True)
    model.report(3,10,'写入',token=token);before=model.state
    assert model.finish(outcome,token=token)
    assert before.phase=='running' and before.current==3
    assert model.state.fraction==(1. if outcome=='complete' else .3)
    result=model.state
    assert not model.report(9,10,'迟到回调',token=token)
    assert not model.finish('complete',token=token) and not model.request_cancel(token=token)
    assert model.state is result


def test_unknown_totals_cancellation_wait_and_normalized_bounds():
    model=ProgressModel();token=model.begin('准备影像','preparation',cancellable=True)
    model.report(-3,-1,'读取');assert model.state.current==0 and model.state.fraction is None
    model.report(50,10,'缓存');assert model.state.current==10 and model.state.fraction==1.
    assert model.request_cancel(token=token) and model.state.phase=='running' and model.state.cancelling
    assert not model.state.can_cancel and not model.report(2,8,'旧进度',token=token)
    assert model.finish('complete',token=token) and model.state.phase=='cancelled'


def test_retry_ignores_prior_generation_and_different_operations_are_independent():
    main=ProgressModel();background=ProgressModel()
    old=main.begin('旧项目','project_open');main.finish('failed')
    current=main.begin('新项目','project_open');background.begin('自动保存','autosave')
    main.report(2,6,'读取标签',token=current);state=main.state
    assert not main.report(99,100,'旧项目回调',token=old)
    assert not main.finish('failed',token=old) and main.state is state
    background.finish('complete')
    assert main.state.phase=='running' and main.state.current==2 and main.state.title=='新项目'
    assert background.state.phase=='complete' and background.state.title=='自动保存'


def test_uncancellable_cleanup_cannot_be_presented_as_cancelled_by_a_request():
    model=ProgressModel();model.begin('退出清理','shutdown')
    assert not model.request_cancel() and model.state.phase=='running'
    model.finish('complete');assert model.state.phase=='complete'


@pytest.mark.parametrize('variant',['light','dark'])
def test_shared_renderer_animates_only_when_required_and_keeps_completion(variant):
    app=QApplication.instance() or QApplication([]);bar=TaskProgressBar(variant=variant)
    bar.show();bar.model.begin('读取影像','import',cancellable=True);app.processEvents()
    try:
        assert bar.timer.isActive() and bar.maximum()==0 and bar.accessibleName()=='读取影像'
        frame=bar.grab().toImage();QTest.qWait(80);app.processEvents();assert frame!=bar.grab().toImage()
        bar.hide();assert not bar.timer.isActive()
        bar.show();app.processEvents();assert bar.timer.isActive()
        bar.model.report(3,8,'读取文件');assert not bar.timer.isActive() and bar.value()==3 and bar.maximum()==8
        bar.model.finish('complete');assert bar.value()==100 and bar.phase=='complete' and not bar.timer.isActive()
        bar.hide();bar.show();app.processEvents();assert bar.phase=='complete' and not bar.timer.isActive()
    finally:bar.close()


@pytest.mark.parametrize('variant',['light','dark'])
def test_smooth_renderer_interpolates_without_changing_model_counts_and_notifies_after_full_paint(variant):
    app=QApplication.instance() or QApplication([]);bar=TaskProgressBar(variant=variant,smooth=True)
    bar.show();app.processEvents();bar.model.begin('test','startup');bar.model.report(1,4,'stage')
    animation=bar.fill_animation;animation.pause();animation.setCurrentTime(animation.duration()//2)
    assert bar.value()==1 and bar.maximum()==4 and 0<bar.display_fraction<.25
    intermediate=bar.display_fraction;bar.model.report(3,4,'next');animation.pause()
    assert bar.display_fraction==intermediate
    animation.setCurrentTime(animation.duration()//2);assert intermediate<bar.display_fraction<.75
    painted=[];bar.completionPainted.connect(lambda:painted.append(bar.display_fraction))
    bar.model.finish('complete');animation.pause();app.processEvents()
    assert bar.display_fraction<1 and not painted and bar.value()==100
    animation.setCurrentTime(animation.duration());bar.repaint();app.processEvents()
    assert painted==[1.]
    bar.hide();bar.show();app.processEvents();assert painted==[1.]
    bar.close()


def test_completion_shortens_an_unfinished_stage_animation_before_the_painted_handoff():
    app=QApplication.instance() or QApplication([]);bar=TaskProgressBar(smooth=True)
    bar.show();app.processEvents();bar.model.begin('test','startup');bar.model.report(6,6,'ready')
    animation=bar.fill_animation;animation.pause();animation.setCurrentTime(0)
    assert animation.duration()>80 and bar.display_fraction==0
    bar.model.finish('complete');animation.pause()
    assert animation.duration()<=80 and bar.display_fraction==0
    painted=[];bar.completionPainted.connect(lambda:painted.append(True));bar.repaint();app.processEvents();assert not painted
    animation.setCurrentTime(animation.duration());bar.repaint();app.processEvents()
    assert painted and bar.display_fraction==1.;bar.close()
