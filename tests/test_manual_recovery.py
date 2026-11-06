import os,time
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtWidgets import QApplication
from geoforma.window import MainWindow
from geoforma.domain import new_project
from geoforma.storage import save_project,load_project
from geoforma.model_preferences import application_settings


@pytest.fixture
def workspace(tmp_path,monkeypatch):
    monkeypatch.setenv('GEOFORMA_DATA_DIR',str(tmp_path/'data'))
    app=QApplication.instance() or QApplication([]);w=MainWindow(auto_prepare=False)
    yield w,app,tmp_path
    w.project_saves.pending.clear();w.project_saves.failed.clear();w.image=None;w.dirty=False;w.close();app.processEvents()


def test_empty_untitled_recovery_is_not_offered_or_overwritten(workspace):
    w,app,tmp=workspace;path=tmp/'data'/'recovery'/'untitled.gfm'
    old=new_project();old['classes'][0]['name']='恢复类别';old['workspace']['single_polygon']=True
    save_project(old,path);w.settings.setValue('recovery/last_work',str(path));original=path.read_bytes()
    app.processEvents();assert w.classes.currentText()=='类别 1' and not w.project['images']
    w.update_controls();assert not w.recover_button.isEnabled()
    w.mark_dirty();w.autosave();assert w.autosave_task is None and path.read_bytes()==original
    w.dirty=False


def test_no_record_disables_button_and_existing_work_cannot_be_replaced(workspace):
    w,app,tmp=workspace;assert not w.recover_button.isEnabled()
    path=tmp/'previous.gfm';save_project(new_project(),path);w.settings.setValue('recovery/last_work',str(path))
    w.project['images']=[{'id':'image','path':'source.tif'}];w.update_controls()
    opened=[];w.open_project=lambda *args,**kwargs:opened.append((args,kwargs))
    assert not w.recover_button.isEnabled();w.recover_previous_work();assert not opened


def test_missing_formal_project_disables_recovery_even_with_sidecar(workspace):
    w,app,tmp=workspace;path=tmp/'saved.gfm';Path(str(path)+'.autosave').write_text('{}')
    w.settings.setValue('recovery/last_work',str(path));assert w.previous_work() is None
    calls=[];w.request_project_open=lambda *args,**kwargs:calls.append((args,kwargs))
    w.update_controls();assert not w.recover_button.isEnabled();w.recover_button.click();assert not calls


def test_unrecorded_recovery_is_not_offered_and_recorded_untitled_wins(workspace):
    w,app,tmp=workspace;root=tmp/'data';unsaved=root/'recovery'/'untitled.gfm';formal=tmp/'saved.gfm'
    w.settings.remove('recovery/last_work')
    save_project(new_project(),formal);project=new_project();project['images']=[{'id':'image','path':'source.tif'}];save_project(project,unsaved)
    os.utime(unsaved,ns=(100,100));os.utime(formal,ns=(200,200));w.settings.setValue('last_project',str(formal))
    assert w.previous_work() is None
    w.settings.setValue('recovery/last_work',str(unsaved))
    assert w.previous_work()==unsaved
    Path(str(formal)+'.autosave').write_text('{}');assert w.previous_work()==unsaved


def test_successful_autosave_records_recovery_entry(workspace):
    w,app,tmp=workspace;w.project['images']=[{'id':'image','path':'source.tif'}];w.mark_dirty();w.autosave()
    deadline=time.monotonic()+4
    while w.autosave_task and time.monotonic()<deadline:app.processEvents();time.sleep(.002)
    assert w.autosave_task is None
    path=tmp/'data'/'recovery'/'untitled.gfm'
    assert w.settings.value('recovery/last_work')==str(path) and path.is_file()
    w.project['classes'][0]['name']='再次修改';w.mark_dirty();w.autosave()
    deadline=time.monotonic()+4
    while w.autosave_task and time.monotonic()<deadline:app.processEvents();time.sleep(.002)
    import json
    assert json.loads(path.read_text(encoding='utf-8'))['classes'][0]['name']=='再次修改'
    assert not (path.parent/(path.name+'.bak')).exists()


def test_unavailable_resource_aborts_shutdown_without_losing_dirty_work(workspace,monkeypatch):
    from geoforma.resource_location import set_resource_parent
    from PySide6.QtWidgets import QMessageBox
    w,app,tmp=workspace
    parent=tmp/'chosen';parent.mkdir();selected=set_resource_parent(parent)
    (selected/'.geoforma-resources').unlink()
    warnings=[];monkeypatch.setattr(QMessageBox,'warning',lambda *args:warnings.append(args))
    w.project['images']=[{'id':'image','path':'source.tif'}];w.mark_dirty()
    w.closing=True;w.autosave()
    deadline=time.monotonic()+5
    while w.autosave_task and time.monotonic()<deadline:app.processEvents();time.sleep(.002)
    app.processEvents()
    assert w.autosave_task is None and w.dirty and not w.closing and warnings


def test_formal_save_records_recovery_entry(workspace):
    w,app,tmp=workspace;w.project_path=tmp/'saved.gfm';w.save()
    assert w.settings.value('recovery/last_work')==str(w.project_path)
    assert not w.recover_button.isEnabled()
