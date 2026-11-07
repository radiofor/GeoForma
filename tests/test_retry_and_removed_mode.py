from types import MethodType
import pytest
from PySide6.QtTest import QTest
from geoforma.controllers.tasks import TaskWorkflow
from geoforma.inference.client import ModelService
from geoforma.inference.engine import ModelEngine
from test_workbench import workbench,fake_image


def test_user_can_retry_failed_model_operation_without_modal_dialog(workbench,monkeypatch):
    from geoforma.controllers import models
    w,app,wait,errors=workbench;attempts=[]
    w.error=MethodType(TaskWorkflow.error,w)
    w.service.activate_project=lambda *a:False
    monkeypatch.setattr(w,'ensure_model_resources',lambda:True)
    monkeypatch.setattr(models,'ModelDialog',lambda *args:None)
    monkeypatch.setattr(models,'dialog_result',lambda *args:(True,dict(w.project['model'])))
    w.image=fake_image('one');w.project['images']=[w.image]
    def operation(config,task):
        attempts.append(task)
        if len(attempts)==1:raise OSError('download timed out')
        return {'checkpoint':config['checkpoint'],'device':'cpu','execution':'native'}
    w.service.prepare_model=operation
    w.configure_model();wait()
    assert len(attempts)==1 and w.progress.phase=='failed'
    assert w.statusBar()._error_toast.label.isVisible() and '模型加载失败' in w.statusBar()._error_toast.label.text()
    w.configure_model();wait()
    assert len(attempts)==2 and attempts[0] is not attempts[1]
    assert w.progress.phase=='complete' and not w.last_error


def test_replaced_project_does_not_trigger_automatic_retry(workbench,monkeypatch):
    w,app,wait,errors=workbench;attempts=[]
    w.error=MethodType(TaskWorkflow.error,w);w.service.activate_project=lambda *a:False
    monkeypatch.setattr(w,'ensure_model_resources',lambda:True)
    def operation(task):attempts.append(task);raise OSError('download timed out')
    w.run('加载模型',operation,lambda _:None,kind='model');wait()
    assert len(attempts)==1 and w.progress.phase=='failed'
    assert w.statusBar()._error_toast.label.isVisible()
    previous_epoch=w.project_epoch;w.new();assert w.project_epoch==previous_epoch+1
    QTest.qWait(250);app.processEvents()
    assert len(attempts)==1 and w.task is None


def test_whole_image_mode_has_no_entry_or_service_execution(workbench):
    w,app,wait,errors=workbench
    assert not hasattr(w,'tabs')
    assert w.mode_index==0 and w.mode_settings.currentWidget() is w.prompt_group
    assert not hasattr(w,'auto_group') and not hasattr(w,'auto_regenerate')
    assert not hasattr(w,'automatic')
    assert not hasattr(ModelService(),'automatic')
    with pytest.raises(ValueError,match='已移除'):ModelEngine().predict(None,None,{'full_image':True},None)


def test_confirmed_labels_remain_available(workbench):
    w,app,wait,errors=workbench
    image=fake_image('one');w.project['images']=[image];w.image=image
    w.project['labels']=[{'id':'saved','image_id':'one','annotation_mode':'individual','status':'confirmed'}]
    assert list(w.current_labels())==w.project['labels']
