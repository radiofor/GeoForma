"""Per-profile and per-model availability, independent of the selected option."""
import copy
from pathlib import Path
import pytest
from PySide6.QtTest import QSignalSpy
from geoforma import native_runtime,resource_state
from geoforma.model_catalog import MODELS
from geoforma.ui.resources import ResourceDialog
from test_workbench import workbench
from test_optional_resources import install,Task


@pytest.fixture
def weights_catalog(tmp_path,monkeypatch):
    specs=tuple(dict(spec,bytes=size) for spec,size in zip((MODELS[0],MODELS[1],MODELS[-1]),(8,10,12)))
    def find(variant,backend='sam'):
        return next(item for item in specs if item['variant']==variant and item['backend']==backend)
    monkeypatch.setenv('GEOFORMA_DATA_DIR',str(tmp_path/'data'))
    monkeypatch.setattr(resource_state,'MODELS',specs);monkeypatch.setattr(resource_state,'model_spec',find)
    monkeypatch.setattr(resource_state,'default_checkpoint',lambda variant,backend:tmp_path/find(variant,backend)['file'])
    monkeypatch.setattr(native_runtime,'status',lambda:dict(ready=False,source='missing',title='未配置'))
    monkeypatch.setattr(native_runtime,'installed_runtimes',lambda:[])
    return specs,tmp_path


def config(spec,path=None):
    return dict(backend=spec['backend'],variant=spec['variant'],device='cuda',checkpoint=str(path or ''))


def test_models_distinguish_configured_partial_local_and_other_variants(weights_catalog):
    specs,folder=weights_catalog
    (folder/specs[0]['file']).write_bytes(b'x'*8);(folder/specs[1]['file']).write_bytes(b'x')
    report=resource_state.inventory(config(specs[0]));states=report['models']
    assert [states[item['id']]['availability'] for item in specs]==['configured','incomplete','missing']
    assert states[specs[0]['id']]['current'] and not states[specs[1]['id']]['current']
    local=folder/'custom.pt';local.write_bytes(b'local')
    state=resource_state.checkpoint_state(config(specs[2],local))
    assert state['availability']=='local' and state['path']==str(local)
    # The preceding model's official file cannot mark this model as configured.
    state=resource_state.checkpoint_state(config(specs[1],folder/specs[0]['file']))
    assert state['availability']=='incomplete' and not state['ready']


def test_inactive_runtime_remains_available_and_caches_do_not_count(install):
    _,sources=install;manager=native_runtime.NativeRuntimeManager()
    cpu=manager.install('cpu',Task(),sources);gpu=manager.install('cu126',Task(),sources)
    states=native_runtime.installed_runtimes()
    assert states[0]['generation']==gpu['generation']
    assert {state['profile'] for state in states}=={'cpu','cu126'}
    assert next(state for state in states if state['profile']=='cpu')['generation']==cpu['generation']
    # Both cached wheel files remain, but neither is an installation record.
    native_runtime.runtime_root().joinpath('current.json').unlink()
    native_runtime.runtime_root().joinpath(cpu['generation'],'installed.json').unlink()
    native_runtime.runtime_root().joinpath(gpu['generation'],'installed.json').unlink()
    assert list((native_runtime.runtime_root()/'downloads').glob('*.whl'))
    assert native_runtime.installed_runtimes()==[]


def test_bundled_pytorch_marks_only_its_matching_profile(weights_catalog,monkeypatch):
    specs,_=weights_catalog
    monkeypatch.setattr(native_runtime,'status',lambda:dict(ready=True,source='bundled',title='现有运行环境'))
    monkeypatch.setattr('importlib.metadata.version',lambda name:'2.13.0+cu126')
    report=resource_state.inventory(config(specs[0]))
    assert report['runtime']['active_profile']=='cu126'
    assert report['profiles']['cu126']['configured'] and report['profiles']['cu126']['current']
    assert not report['profiles']['cpu']['configured'] and not report['profiles']['cpu']['current']
    monkeypatch.setattr('importlib.metadata.version',lambda name:'2.14.0+cu130')
    report=resource_state.inventory(config(specs[0]))
    assert report['runtime']['ready'] and report['runtime']['active_profile'] is None
    assert not any(item['configured'] for item in report['profiles'].values())


def test_dropdowns_show_independent_states_and_browsing_keeps_active_config(workbench,weights_catalog,monkeypatch):
    from geoforma.ui import resources
    w,app,wait,errors=workbench;specs,folder=weights_catalog
    monkeypatch.setattr(resources,'MODELS',specs)
    monkeypatch.setattr(native_runtime,'status',lambda:dict(ready=True,source='managed',profile='cu126',title='NVIDIA GPU'))
    monkeypatch.setattr(native_runtime,'installed_runtimes',lambda:[dict(profile='cu126'),dict(profile='cpu')])
    (folder/specs[0]['file']).write_bytes(b'x'*8)
    w.project['model']=config(specs[0]);original=copy.deepcopy(w.project['model']);queries=[]
    def query(cfg):queries.append(True);return resource_state.inventory(cfg)
    monkeypatch.setattr(resources,'inventory',query)
    dialog=ResourceDialog(w);dialog.show();app.processEvents()
    try:
        initial=(dialog.size(),dialog.model.geometry(),dialog.details.geometry())
        assert dialog.weight_status.text()==specs[0]['title'] and '已就绪' not in dialog.weight_status.text()
        assert '已配置' in dialog.model.itemText(0) and '未配置' in dialog.model.itemText(1)
        dialog.model.setCurrentIndex(1);app.processEvents()
        assert '未配置' in dialog.weight_detail.text()
        assert dialog.weight_status.text()==specs[0]['title'] and w.project['model']==original
        assert len(queries)==1 and initial==(dialog.size(),dialog.model.geometry(),dialog.details.geometry())
        model_spy=QSignalSpy(dialog.model.currentIndexChanged)
        (folder/specs[1]['file']).write_bytes(b'x'*10);dialog.reload_inventory();app.processEvents()
        assert dialog.model.currentIndex()==1 and '已配置' in dialog.model.currentText()
        assert model_spy.count()==0
        assert '已配置' in dialog.weight_detail.text() and not errors
        dialog.resize(680,580);app.processEvents()
        assert dialog.weight_detail.geometry().bottom()<dialog.weight_download.geometry().top()
        assert dialog.details.geometry().bottom()<dialog.close_button.geometry().top()
    finally:dialog.accept();dialog.deleteLater()
