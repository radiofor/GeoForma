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


def test_legacy_project_uses_auto_without_changing_label_provenance(tmp_path):
    from geoforma.storage import load_project
    from geoforma.workflow import fully_prepared,preparation_signature
    from shapely.geometry import box,mapping
    project=new_project();project['model']['execution']='wsl'
    project['images']=[dict(id='image',path='source.tif',name='source.tif',width=10,height=10,transform=[1,0,0,0,-1,10],bands=3,dtypes=['uint8'],crs='EPSG:3857',fingerprint='legacy',source_files=1)]
    project['images'][0]['ready']=True
    project['images'][0]['prepared_full_signature']=preparation_signature(project['images'][0],project['model'])
    project['labels']=[dict(id='saved',image_id='image',model={'execution':'wsl'},status='confirmed',geometry=mapping(box(1,1,5,5)))]
    path=tmp_path/'legacy.geoforma.json';path.write_text(json.dumps(project),encoding='utf-8')
    loaded=load_project(path)
    assert loaded['model']['execution']=='auto'
    assert fully_prepared(loaded['images'][0],loaded['model'])
    assert loaded['labels'][0]['model']==project['labels'][0]['model']
    assert loaded['labels'][0]['annotation_mode']=='individual'


def test_model_dialog_has_no_runtime_selector():
    from PySide6.QtWidgets import QApplication
    from geoforma.dialogs import ModelDialog
    app=QApplication.instance() or QApplication([])
    dialog=ModelDialog(new_project()['model'])
    assert not hasattr(dialog,'execution') and dialog.value()['execution']=='auto'
    dialog.close()
