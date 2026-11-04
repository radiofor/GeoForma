from types import MethodType
import pytest
from PySide6.QtWidgets import QMessageBox
from geoforma.controllers.tasks import TaskWorkflow
from geoforma.inference.client import ModelService
from geoforma.inference.engine import ModelEngine
from test_workbench import workbench,fake_image


def test_retry_repeats_failed_model_operation(workbench,monkeypatch):
    w,app,wait,errors=workbench;attempts=[];results=[];dialogs=[]
    w.error=MethodType(TaskWorkflow.error,w)
    w.service.activate_project=lambda *a:False
    def dialog(box,value=None,owner=None):
        dialogs.append(box)
        assert box.button(QMessageBox.StandardButton.Retry).text()=='重试'
        box.button(QMessageBox.StandardButton.Retry).click()
        return True,value(box)
    monkeypatch.setattr('geoforma.controllers.tasks.dialog_result',dialog)
    def operation(task):
        attempts.append(task)
        if len(attempts)==1:raise OSError('download timed out')
        return 'ready'
    assert w.run('加载模型',operation,results.append,kind='model')
    wait()
    assert len(attempts)==2 and attempts[0] is not attempts[1]
    assert results==['ready'] and len(dialogs)==1 and not w.last_error


def test_retry_ignores_a_replaced_project(workbench,monkeypatch):
    w,app,wait,errors=workbench;attempts=[]
    w.error=MethodType(TaskWorkflow.error,w);w.service.activate_project=lambda *a:False
    def dialog(box,value=None,owner=None):
        w.project_epoch+=1;box.button(QMessageBox.StandardButton.Retry).click()
        return True,value(box)
    monkeypatch.setattr('geoforma.controllers.tasks.dialog_result',dialog)
    def operation(task):attempts.append(task);raise OSError('download timed out')
    w.run('加载模型',operation,lambda _:None,kind='model');wait()
    assert len(attempts)==1


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
