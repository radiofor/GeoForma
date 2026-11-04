"""Regressions for release integrity, inaccessible resources and stale callbacks."""
import threading,time
from pathlib import Path
import pytest
from geoforma import native_runtime,resource_state
from geoforma.release_artifacts import release_inventory,verify_release_inventory
from geoforma.ui.resources import ResourceDialog
from geoforma.controllers.projects import ProjectWorkflow
from test_resource_inventory import weights_catalog,config
from test_workbench import workbench,fake_image


def test_workbench_controllers_do_not_shadow_each_others_operations():
    from collections import defaultdict
    from types import FunctionType
    from geoforma.window import MainWindow
    owners=defaultdict(list)
    controllers=(MainWindow,*(base for base in MainWindow.__bases__ if base.__module__.startswith('geoforma.controllers')))
    for controller in controllers:
        for name,value in vars(controller).items():
            if not name.startswith('__') and isinstance(value,(FunctionType,property,staticmethod,classmethod)):
                owners[name].append(controller.__name__)
    assert not {name:classes for name,classes in owners.items() if len(classes)>1}


def test_release_verifier_checks_content_not_just_size_and_excludes_its_manifest(tmp_path):
    program=tmp_path/'GeoForma.exe';program.write_bytes(b'original');records=release_inventory(tmp_path)
    (tmp_path/'release-manifest.json').write_text('manifest is excluded from its own payload hash')
    assert verify_release_inventory(tmp_path,records)==1
    program.write_bytes(b'modified')
    with pytest.raises(ValueError,match='内容'):verify_release_inventory(tmp_path,records)


@pytest.mark.parametrize('change',['added','missing','duplicate','traversal','hash','bool_size'])
def test_release_verifier_rejects_unlisted_files_and_invalid_records(tmp_path,change):
    program=tmp_path/'GeoForma.exe';program.write_bytes(b'program');records=release_inventory(tmp_path)
    if change=='added':tmp_path.joinpath('unexpected.dll').write_bytes(b'extra')
    elif change=='missing':program.unlink()
    elif change=='duplicate':records.append(dict(records[0],path='GEOFORMA.EXE'))
    elif change=='traversal':records[0]['path']='../GeoForma.exe'
    elif change=='hash':records[0]['sha256']='invalid'
    else:records[0]['bytes']=True
    with pytest.raises(ValueError):verify_release_inventory(tmp_path,records)


def test_release_verifier_rejects_linked_subdirectories(tmp_path,monkeypatch):
    folder=tmp_path/'linked';folder.mkdir();(folder/'program.dll').write_bytes(b'program')
    records=release_inventory(tmp_path);original=Path.is_junction
    monkeypatch.setattr(Path,'is_junction',lambda path:path==folder or original(path))
    with pytest.raises(ValueError,match='链接'):verify_release_inventory(tmp_path,records)


def test_resource_access_errors_do_not_escape_inventory_or_break_dialog(workbench,weights_catalog,monkeypatch):
    from geoforma.ui import resources
    w,app,wait,errors=workbench;specs,folder=weights_catalog;denied=folder/specs[0]['file']
    original=Path.is_file
    def is_file(path):
        if path==denied:raise PermissionError('permission denied')
        return original(path)
    monkeypatch.setattr(Path,'is_file',is_file);monkeypatch.setattr(resources,'MODELS',specs)
    w.project['model']=config(specs[0],denied)
    state=resource_state.checkpoint_state(w.project['model'])
    assert not state['ready'] and state['availability']=='unavailable' and 'permission' in state['error']
    dialog=ResourceDialog(w)
    try:
        assert '无法访问' in dialog.model.currentText() and '访问权限' in dialog.weight_detail.text()
        assert dialog.close_button.isEnabled() and not errors
    finally:dialog.accept();dialog.deleteLater()


def test_runtime_read_queries_survive_unavailable_data_root(monkeypatch):
    def denied():raise PermissionError('data root unavailable')
    monkeypatch.setattr(native_runtime,'runtime_root',denied)
    monkeypatch.setattr(native_runtime,'lightweight',lambda:True)
    assert native_runtime.managed_runtime() is None and native_runtime.installed_runtimes()==[]
    assert not native_runtime.status()['ready']


def test_default_checkpoint_resolution_failure_and_model_dialog_share_status(weights_catalog,monkeypatch):
    from geoforma import model_status
    specs,folder=weights_catalog
    def denied(*args):raise PermissionError('model folder unavailable')
    monkeypatch.setattr(resource_state,'default_checkpoint',denied)
    state=resource_state.checkpoint_state(config(specs[0]))
    assert state['availability']=='unavailable' and not state['ready']
    monkeypatch.setattr(model_status,'default_checkpoint',denied)
    assert model_status.weight_status(specs[0])[0]=='无法访问'
    path=folder/'renamed.pt';path.write_bytes(b'x'*specs[0]['bytes'])
    assert model_status.weight_status(specs[0],path)[0]=='本地待校验'


def test_old_project_autosave_completion_does_not_overwrite_current_status(workbench,monkeypatch,tmp_path):
    w,app,wait,errors=workbench;started=threading.Event();release=threading.Event()
    w.project_path.write_text('{}')
    def write(project,path,**kwargs):started.set();release.wait(5)
    monkeypatch.setattr('geoforma.controllers.projects.save_project',write)
    w.project['images']=[fake_image('old')];w.mark_dirty();ProjectWorkflow.autosave(w)
    try:
        deadline=time.monotonic()+3
        while not started.is_set():app.processEvents();time.sleep(.002);assert time.monotonic()<deadline
        w.project_epoch+=1;w.project_path=tmp_path/'new.gfm';w.mark_dirty()
        w.statusBar().showMessage('新项目编辑中',10000);release.set();wait()
        assert w.statusBar().currentMessage()=='新项目编辑中' and w.dirty and not errors
    finally:release.set();wait()
