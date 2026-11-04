import json
import pytest
from geoforma.domain import new_project
from geoforma.execution_policy import resolve_execution


@pytest.mark.parametrize('family,variant',[('sam','vit_b'),('sam2','tiny'),('sam2.1','small'),('sam3','interactive')])
def test_auto_prefers_native_when_available(family,variant,monkeypatch):
    monkeypatch.setattr('geoforma.execution_policy.native_available',lambda family:True)
    assert resolve_execution(dict(backend=family,variant=variant,execution='auto'))=='native'


def test_auto_remains_native_when_runtime_is_not_installed(monkeypatch):
    monkeypatch.setattr('geoforma.execution_policy.native_available',lambda family:False)
    assert resolve_execution(new_project()['model'])=='native'


def test_explicit_old_backend_cannot_start():
    with pytest.raises(ValueError,match='Windows 原生'):
        resolve_execution(dict(backend='sam',variant='vit_b',execution='wsl'))


def test_project_rejects_removed_runtime(tmp_path):
    from geoforma.storage import load_project
    project=new_project();project['model']['execution']='wsl'
    path=tmp_path/'invalid.gfm';path.write_text(json.dumps(project),encoding='utf-8')
    with pytest.raises(ValueError,match='模型配置无效'):load_project(path)


def test_model_dialog_has_no_runtime_selector():
    from PySide6.QtWidgets import QApplication
    from geoforma.dialogs import ModelDialog
    app=QApplication.instance() or QApplication([])
    dialog=ModelDialog(new_project()['model'])
    assert not hasattr(dialog,'execution') and dialog.value()['execution']=='auto'
    dialog.close()
