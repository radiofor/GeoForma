"""Project changes remove disposable data while preserving source and saved work."""
import copy,json,os,threading,time
from pathlib import Path
import numpy as np
import pytest
from geoforma.project_cache import activate_project_cache,clear_image_cache
from geoforma.inference.client import ModelService
from geoforma.domain import data_dir,new_project
from geoforma.storage import save_project,load_project
from test_workbench import workbench,fake_image
from test_project_loading import saved_project
from test_reshape import raster_image
from test_background_activity import until
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest


def feature(root,key='a'):
    path=root/'cache/features'/(key*64+'.pt');path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'features');return path


def test_owner_switch_deletes_features_automatic_and_abandoned_temporaries(tmp_path):
    root=tmp_path;activate_project_cache(root,'a'*32)
    main=feature(root)
    automatic=root/'cache/automatic'/('b'*64+'.json');automatic.parent.mkdir();automatic.write_text('{}')
    partial=main.with_name('.'+main.name+'.abcd1234.tmp');partial.write_bytes(b'partial')
    exchange=root/'runtime/exchange/worker_abcd'/('f'*32);exchange.mkdir(parents=True)
    npz=exchange/'input.npz';npz.write_bytes(b'npz');(exchange.parent/'worker.log').write_text('log')
    protected=[]
    for relative in ('models/model.pt','recovery/work.json','labels.geoforma.json','source.tif','cache/features/user.tif'):
        path=root/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'preserve');protected.append(path)
    assert not activate_project_cache(root,'a'*32)['cleared'] and main.exists()
    result=activate_project_cache(root,'b'*32)
    assert result['cleared'] and not any(p.exists() for p in (main,automatic,partial,npz))
    assert not exchange.parent.exists() and all(p.read_bytes()==b'preserve' for p in protected)
    assert json.loads((root/'cache/active-project.json').read_text())['owner']=='b'*32


def test_failed_cleanup_does_not_publish_new_owner(tmp_path,monkeypatch):
    activate_project_cache(tmp_path,'a'*32);path=feature(tmp_path);original=Path.unlink
    def unlink(self,*args,**kwargs):
        if self==path:raise PermissionError('busy cache')
        return original(self,*args,**kwargs)
    monkeypatch.setattr(Path,'unlink',unlink)
    with pytest.raises(PermissionError):activate_project_cache(tmp_path,'b'*32)
    assert json.loads((tmp_path/'cache/active-project.json').read_text())['owner']=='a'*32


def test_cache_cleanup_refuses_directory_junction(tmp_path,monkeypatch):
    path=feature(tmp_path);target=path.parent;original=Path.is_junction
    monkeypatch.setattr(Path,'is_junction',lambda self:self==target or original(self))
    with pytest.raises(ValueError):clear_image_cache(tmp_path)
    assert path.exists()


def test_service_stops_previous_writer_before_removing_cache(tmp_path,monkeypatch):
    activate_project_cache(tmp_path,'a'*32);path=feature(tmp_path)
    service=ModelService();events=[]
    def close():
        assert path.exists();events.append('stopped')
    monkeypatch.setattr(service,'close',close)
    assert service.activate_project(tmp_path,'b'*32)
    assert events==['stopped'] and not path.exists()
    feature(tmp_path)
    assert not service.activate_project(tmp_path,'b'*32) and events==['stopped']


def test_cache_id_survives_save_as_and_old_project_recovery(tmp_path):
    project=new_project();path=tmp_path/'one.geoforma.json';save_project(project,path)
    second=tmp_path/'two.geoforma.json';save_project(load_project(path),second)
    assert load_project(path)['cache_id']==load_project(second)['cache_id']==project['cache_id']
    old=copy.deepcopy(project);old.pop('cache_id');path.write_text(json.dumps(old))
    Path(str(path)+'.autosave').write_text(json.dumps(old))
    Path(str(path)+'.autosave.bak').write_text(json.dumps(old))
    assert load_project(path)['cache_id']==load_project(str(path)+'.autosave')['cache_id']
    assert load_project(path)['cache_id']==load_project(str(path)+'.autosave.bak')['cache_id']


def test_replacing_cache_changes_revision_even_when_the_same_project_returns(tmp_path):
    first=activate_project_cache(tmp_path,'a'*32)
    assert activate_project_cache(tmp_path,'a'*32)['revision']==first['revision']
    activate_project_cache(tmp_path,'b'*32)
    last=activate_project_cache(tmp_path,'a'*32)
    assert first['revision']!=last['revision'] and last['cleared']


def test_reopening_same_project_removes_only_abandoned_temps_without_invalidating_features(tmp_path):
    root=tmp_path;owner='a'*32;first=activate_project_cache(root,owner)
    valid=feature(root);stale=valid.with_name('.'+valid.name+'.abcd1234.tmp');stale.write_bytes(b'old')
    fresh=valid.with_name('.'+valid.name+'.abcd5678.tmp');fresh.write_bytes(b'fresh')
    unknown=valid.with_name('.user-file.abcd1234.tmp');unknown.write_bytes(b'user')
    old=time.time()-8*86400
    for path in (stale,unknown):os.utime(path,(old,old))
    service=ModelService();service.cache_generation=4
    assert not service.activate_project(root,owner)
    assert service.cache_revision==first['revision'] and service.cache_generation==4
    assert valid.exists() and fresh.exists() and unknown.exists() and not stale.exists()


def test_feature_cache_rejects_linked_directories_and_files(tmp_path,monkeypatch):
    from geoforma.feature_cache import feature_directory,feature_path
    directory=tmp_path/'cache'/'features';directory.mkdir(parents=True)
    target=directory/(('a'*64)+'.pt');original=Path.is_junction
    monkeypatch.setattr(Path,'is_junction',lambda path:path==directory or original(path))
    with pytest.raises(ValueError,match='缓存目录'):feature_directory(tmp_path)
    monkeypatch.setattr(Path,'is_junction',lambda path:path==target or original(path))
    with pytest.raises(ValueError,match='链接'):feature_path(tmp_path,'a'*64)
    with pytest.raises(ValueError,match='标识'):feature_path(tmp_path,'../not-a-key')


def test_desktop_session_excludes_other_processes_using_same_data_directory(tmp_path):
    import subprocess,sys
    from geoforma.session_guard import desktop_session
    script="from geoforma.session_guard import desktop_session\nimport sys\nwith desktop_session(sys.argv[1]) as ok: print(int(ok))"
    def attempt():
        result=subprocess.run([sys.executable,'-c',script,str(tmp_path)],capture_output=True,text=True,check=True,
                              creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        return result.stdout.strip()
    with desktop_session(tmp_path) as acquired:
        assert acquired and attempt()=='0'
    assert attempt()=='1'


@pytest.mark.parametrize('arguments',[
    ['--runtime-command','cleanup-cache'],
    ['--self-test','REPORT','--resource-command','status'],
])
def test_cli_mutation_cannot_run_while_desktop_owns_data(tmp_path,arguments):
    import os,subprocess,sys
    from geoforma.session_guard import desktop_session
    root=tmp_path/'data';root.mkdir();cache=feature(root);report=tmp_path/'report.json'
    env=dict(os.environ,GEOFORMA_DATA_DIR=str(root),QT_QPA_PLATFORM='offscreen')
    arguments=[str(report) if value=='REPORT' else value for value in arguments]
    if '--self-test' not in arguments:arguments+=['--output',str(report)]
    with desktop_session(root) as acquired:
        assert acquired
        result=subprocess.run([sys.executable,'main.py',*arguments],
                              env=env,capture_output=True,text=True,timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    assert result.returncode==1 and cache.exists()
    assert json.loads(report.read_text(encoding='utf-8'))['ok'] is False


def test_resource_status_remains_available_while_desktop_owns_data(tmp_path):
    import os,subprocess,sys
    from geoforma.session_guard import desktop_session
    root=tmp_path/'data';root.mkdir();report=tmp_path/'status.json'
    env=dict(os.environ,GEOFORMA_DATA_DIR=str(root),QT_QPA_PLATFORM='offscreen')
    with desktop_session(root) as acquired:
        assert acquired
        result=subprocess.run([sys.executable,'main.py','--resource-command','status','--output',str(report)],
                              env=env,capture_output=True,text=True,timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    assert result.returncode==0 and json.loads(report.read_text(encoding='utf-8'))['ok'] is True


def test_linked_feature_cache_cannot_reach_native_writer(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from geoforma import backend
    from geoforma.backend import SamBackend
    directory=tmp_path/'cache'/'features';directory.mkdir(parents=True)
    original=Path.is_junction
    monkeypatch.setattr(Path,'is_junction',lambda path:path==directory or original(path))
    monkeypatch.setattr(backend,'data_dir',lambda:tmp_path)
    monkeypatch.setenv('GEOFORMA_DATA_DIR',str(tmp_path))
    calls=[];native=SamBackend();native.key=lambda *args:'a'*64
    native.predictor=SimpleNamespace(set_image=lambda *args:calls.append('native'))
    with pytest.raises(ValueError,match='缓存目录'):native.encode({},[0,0,1,1],np.zeros((1,1,3),np.uint8))
    assert not calls


def test_new_project_clears_disk_and_memory_without_touching_source(workbench):
    w,app,wait,errors=workbench;root=data_dir()
    w.service.activate_project(root,w.project['cache_id']);w.cache_generation=w.service.cache_generation
    path=feature(root);old_owner=w.project['cache_id']
    image=fake_image('old');w.project['images']=[image];w.image=image
    w.raster_renderer.prime(image,[0,0,1,1],1,(np.zeros((1,1,3),np.uint8),np.ones((1,1),bool)))
    assert w.raster_renderer.cache
    w.new();wait()
    assert w.project['cache_id']!=old_owner and not w.project['images'] and not path.exists()
    assert not w.raster_renderer.cache and w.raster_renderer.cache_bytes==0
    assert not w.candidate_indexes and not errors


def test_open_other_project_cleans_old_cache_before_preparation(workbench,saved_project):
    w,app,wait,errors=workbench;root=data_dir();w.service.activate_project(root,w.project['cache_id'])
    path=feature(root);new_path,_=saved_project
    assert w.open_project(new_path)
    assert not path.exists() and not any(im['ready'] for im in w.project['images'])
    assert w.project['labels'] and not errors


def test_same_project_keeps_its_valid_preparation_revision(workbench,saved_project):
    w,app,wait,errors=workbench;path,project=saved_project;root=data_dir()
    w.service.activate_project(root,project['cache_id'])
    project['images'][0]['prepared_cache_revision']=w.service.cache_revision
    save_project(project,path);cached=feature(root)
    assert w.open_project(path) and w.image['ready'] and cached.exists() and not errors


def test_invalid_project_does_not_clear_current_cache(workbench,tmp_path):
    w,app,wait,errors=workbench;root=data_dir()
    w.service.activate_project(root,w.project['cache_id']);cached=feature(root)
    path=tmp_path/'invalid.json';path.write_text('invalid')
    assert not w.open_project(path) and cached.exists() and errors


def test_new_project_cleanup_runs_off_ui_thread(workbench,monkeypatch):
    import geoforma.project_cache as module
    w,app,wait,errors=workbench;root=data_dir()
    w.service.activate_project(root,w.project['cache_id']);feature(root)
    started=threading.Event();release=threading.Event();threads=[];original=module.clear_image_cache
    def clear(root):
        threads.append(threading.get_ident());started.set();assert release.wait(5)
        return original(root)
    monkeypatch.setattr(module,'clear_image_cache',clear)
    ticks=[];timer=QTimer();timer.setInterval(10);timer.timeout.connect(lambda:ticks.append(True))
    try:
        timer.start();w.new();until(app,started.is_set)
        QTest.qWait(80)
        assert ticks and threads[0]!=threading.get_ident() and w.task_kind=='cache_cleanup'
        release.set();wait();assert not errors
    finally:release.set();timer.stop()
