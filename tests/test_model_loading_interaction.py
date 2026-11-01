"""Model loading permits browsing without competing tasks or stale draft writes."""
import copy,threading
import pytest
from shapely.geometry import box,mapping
from geoforma.operation_state import can_browse,can_start_operation
from test_background_activity import until
from test_workbench import workbench,fake_image


@pytest.mark.parametrize('kind',['model','model_warmup'])
def test_model_loading_allows_image_mode_and_label_browsing(workbench,kind):
    w,app,wait,errors=workbench;release=threading.Event();started=threading.Event();completed=[]
    images=[dict(fake_image(name),ready=True) for name in ('one','two')]
    w.project['images']=images
    for config in w.project['smoothing'].values():config['enabled']=False
    w.project['labels']=[dict(id='saved',image_id='one',status='confirmed',annotation_mode='individual',class_id=1,geometry=mapping(box(20,20,60,60)))]
    original=copy.deepcopy(w.project['labels']);w.refresh_images();w.images.setCurrentRow(0)
    w.draft={'points':[[80,80,1]],'pending':True};draft=copy.deepcopy(w.draft)
    def load(task):
        started.set();task.signals.progress.emit(0,0,'加载模型权重…')
        while not release.wait(.002):task.check()
        return 'loaded'
    try:
        assert w.run('加载模型',load,completed.append,kind=kind)
        until(app,lambda:started.is_set() and w.task_stage=='加载模型权重…')
        task=w.task
        assert can_browse(w) and not can_start_operation(w)
        for control in (w.images,w.mode_actions['select'],w.mode_actions['pan']):assert control.isEnabled()
        assert not w.project_actions['save'].isEnabled()
        for control in (w.model_button,w.apply_button,w.reprepare_button,w.import_button):assert not control.isEnabled()
        assert not w.run('第二个任务',lambda task:None,lambda result:None,kind='export')
        w.set_tool('select');assert w.view.mode=='select'
        w.select_items('labels',['saved']);assert w.selected_ids=={'saved'} and w.zoom_button.isEnabled()
        w.zoom_button.click();assert w.draft==draft
        w.select_items('points',[0]);assert not w.selected_points
        w.images.setCurrentRow(1);assert w.image is images[1] and not w.draft
        assert not hasattr(w,'tabs') and w.mode_index==0
        w.images.setCurrentRow(0);assert w.image is images[0] and w.draft==draft
        assert w.task is task and w.project['labels']==original and not completed
        release.set();wait()
        assert completed==['loaded'] and w.image is images[0] and w.draft==draft
        assert w.model_button.isEnabled() and not errors
    finally:release.set();wait()


@pytest.mark.parametrize('kind',['interactive','reshape','export','resource_install','history'])
def test_other_tasks_still_block_image_and_mode_changes(workbench,kind):
    w,app,wait,errors=workbench;w.task=object();w.task_kind=kind
    try:
        w.update_controls();assert not can_browse(w)
        assert not w.images.isEnabled() and not w.mode_actions['select'].isEnabled()
        assert not hasattr(w,'switch_annotation_mode') and w.mode_index==0
    finally:w.task=None;w.task_kind=None;w.update_controls()


def test_project_transition_takes_precedence_over_model_browsing(workbench):
    w,app,wait,errors=workbench;w.task=object();w.task_kind='model_warmup';w.loading_task=object()
    try:assert not can_browse(w)
    finally:w.task=None;w.task_kind=None;w.loading_task=None


def test_device_status_follows_first_preparation_and_reused_model(workbench):
    w,app,wait,errors=workbench
    w.project['model']['device']='cuda';w.runtime_status=None
    w.task=object();w.task_kind='preparation'
    try:
        w.update_controls();app.processEvents();assert w.model_runtime.text()=='设备：GPU 优先 · 准备中'
        assert '准备中' in w.model_runtime._display_text and '…' not in w.model_runtime._display_text
        w.task_kind='model';w.update_controls();app.processEvents()
        assert w.model_runtime.text()=='设备：GPU 优先 · 加载中'
        assert '加载中' in w.model_runtime._display_text and '…' not in w.model_runtime._display_text
        w.task_kind='preparation'
        w.record_runtime({'device':'cuda'});w.update_controls()
        assert w.model_runtime.text()=='设备：GPU'
        w.record_runtime({'device':'cpu'});w.task_kind='model';w.update_controls();app.processEvents()
        assert w.model_runtime.text()=='设备：CPU（回退） · 加载中'
        assert '回退' in w.model_runtime._display_text and '加载中' in w.model_runtime._display_text and '…' not in w.model_runtime._display_text
    finally:w.task=None;w.task_kind=None;w.update_controls()
    assert not errors


@pytest.mark.parametrize('worker_survives',[False,True])
def test_device_status_after_model_worker_failure_preserves_ready_image(workbench,monkeypatch,worker_survives):
    w,app,wait,errors=workbench
    image=dict(fake_image('image'),ready=True);w.project['images']=[image];w.image=image
    w.project['model']['device']='cuda';w.record_runtime({'device':'cuda'});w.service.ready=True
    monkeypatch.setattr(w.service,'activate_project',lambda *args:False)
    def fail(task):
        if not worker_survives:w.service.ready=False
        raise RuntimeError('模拟推理失败')
    assert w.run('测试推理',fail,lambda result:None,kind='interactive')
    wait()
    assert image['ready'] and errors
    if worker_survives:
        assert w.runtime_status and w.model_runtime.text()=='设备：GPU'
    else:
        assert w.runtime_status is None and w.model_runtime.text()=='设备：GPU 优先 · 待加载'
