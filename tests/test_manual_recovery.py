import os,time
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtWidgets import QApplication
from geoforma.window import MainWindow
from geoforma.domain import new_project
from geoforma.storage import save_project,load_project
from geoforma.recovery import recovery_target
from geoforma.model_preferences import application_settings


@pytest.fixture
def workspace(tmp_path,monkeypatch):
    monkeypatch.setenv('GEOFORMA_DATA_DIR',str(tmp_path/'data'))
    app=QApplication.instance() or QApplication([]);w=MainWindow(auto_prepare=False)
    yield w,app,tmp_path
    w.project_saves.pending.clear();w.project_saves.failed.clear();w.image=None;w.dirty=False;w.close();app.processEvents()


def test_blank_start_requires_button_and_blank_exit_preserves_recovery(workspace):
    w,app,tmp=workspace;path=tmp/'data'/'recovery'/'untitled.geoforma.json'
    old=new_project();old['classes'][0]['name']='恢复类别';old['workspace']['single_polygon']=True
    save_project(old,path);w.settings.setValue('recovery/last_work',str(path));original=path.read_bytes()
    app.processEvents();assert w.classes.currentText()=='类别 1' and not w.project['images']
    w.update_controls();assert w.recover_button.isEnabled()
    w.mark_dirty();w.autosave();assert w.autosave_task is None and path.read_bytes()==original
    w.dirty=False;w.recover_button.click()
    deadline=time.monotonic()+4
    while w.loading_task or w.project_transition:
        app.processEvents();time.sleep(.002);assert time.monotonic()<deadline
    assert w.classes.currentText()=='恢复类别' and w.single_polygon.isChecked()
    assert w.project_path is None


def test_no_record_disables_button_and_existing_work_cannot_be_replaced(workspace):
    w,app,tmp=workspace;assert not w.recover_button.isEnabled()
    path=tmp/'previous.geoforma.json';save_project(new_project(),path);w.settings.setValue('recovery/last_work',str(path))
    w.project['images']=[{'id':'image','path':'source.tif'}];w.update_controls()
    opened=[];w.open_project=lambda *args,**kwargs:opened.append((args,kwargs))
    assert not w.recover_button.isEnabled();w.recover_previous_work();assert not opened


def test_recovery_finds_autosave_when_formal_project_is_missing(workspace):
    w,app,tmp=workspace;path=tmp/'saved.geoforma.json';save_project(new_project(),str(path)+'.autosave')
    w.settings.setValue('recovery/last_work',str(path));assert w.previous_work()==path
    calls=[];w.request_project_open=lambda *args,**kwargs:calls.append((args,kwargs))
    w.update_controls();w.recover_button.click();assert calls==[((path,),{'recover_latest':True})]


def test_legacy_fallback_chooses_newest_available(workspace):
    w,app,tmp=workspace;root=tmp/'data';unsaved=root/'recovery'/'untitled.geoforma.json';formal=tmp/'saved.geoforma.json'
    save_project(new_project(),formal);save_project(new_project(),unsaved)
    os.utime(formal,ns=(100,100));os.utime(unsaved,ns=(200,200));w.settings.setValue('last_project',str(formal))
    assert w.previous_work()==unsaved
    save_project(new_project(),str(formal)+'.autosave');assert w.previous_work()==formal


def test_successful_autosave_records_recovery_entry(workspace):
    w,app,tmp=workspace;w.project['images']=[{'id':'image','path':'source.tif'}];w.mark_dirty();w.autosave()
    deadline=time.monotonic()+4
    while w.autosave_task and time.monotonic()<deadline:app.processEvents();time.sleep(.002)
    assert w.autosave_task is None
    path=tmp/'data'/'recovery'/'untitled.geoforma.json'
    assert w.settings.value('recovery/last_work')==str(path) and path.is_file()


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
    w,app,tmp=workspace;w.project_path=tmp/'saved.geoforma.json';w.save()
    assert w.settings.value('recovery/last_work')==str(w.project_path)
    assert not w.recover_button.isEnabled()
