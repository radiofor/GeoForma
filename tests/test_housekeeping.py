"""Automatic housekeeping never removes useful or active user data."""
import hashlib
import json
import os
import time
from pathlib import Path
import pytest
from geoforma.housekeeping import clean_download_remnants
from geoforma.resource_lock import try_resource_lock
from test_workbench import workbench
from test_background_activity import until


class Task:
    def check(self):pass


@pytest.fixture
def setup_downloads(tmp_path,monkeypatch):
    from geoforma import model_catalog,native_runtime
    payload=b'official checkpoint'
    spec=dict(file='model.pt',bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest())
    monkeypatch.setattr(model_catalog,'MODELS',(spec,))
    monkeypatch.setattr(native_runtime,'catalog',lambda:dict(profiles={}))
    folder=tmp_path/'models';folder.mkdir()
    target=folder/'model.pt';target.write_bytes(payload)
    partial=folder/'model.pt.part';partial.write_bytes(b'partial')
    metadata=folder/'model.pt.part.json';metadata.write_text('{}')
    for file in (partial,metadata):os.utime(file,(time.time()-172800,)*2)
    for name in ('cache/features/keep.pt','recovery/work.json','models/other.pt.part'):
        file=tmp_path/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(b'keep')
    return target,partial,metadata


def test_duplicate_partial_is_removed_only_after_final_hash_and_dry_run_is_read_only(tmp_path,setup_downloads):
    target,partial,metadata=setup_downloads
    result=clean_download_remnants(tmp_path,Task())
    assert len(result['files'])==2 and target.exists() and partial.exists() and metadata.exists()
    assert sorted(p.name for p in target.parent.iterdir())==['model.pt','model.pt.part','model.pt.part.json','other.pt.part']
    result=clean_download_remnants(tmp_path,Task(),apply=True)
    assert len(result['files'])==2 and not partial.exists() and not metadata.exists()
    assert target.read_bytes()==b'official checkpoint'
    assert (tmp_path/'cache/features/keep.pt').exists() and (tmp_path/'recovery/work.json').exists()
    assert (tmp_path/'models/other.pt.part').exists()


@pytest.mark.parametrize('reason',['missing','wrong_hash','fresh','locked'])
def test_useful_fresh_or_busy_downloads_are_preserved(tmp_path,setup_downloads,reason):
    target,partial,metadata=setup_downloads
    if reason=='missing':target.unlink()
    if reason=='wrong_hash':target.write_bytes(b'x'*len(b'official checkpoint'))
    if reason=='fresh':os.utime(partial,None)
    lock=target.with_suffix('.download.lock')
    if reason=='locked':
        with try_resource_lock(lock) as acquired:
            assert acquired
            result=clean_download_remnants(tmp_path,Task(),apply=True)
    else:result=clean_download_remnants(tmp_path,Task(),apply=True)
    assert not result['files'] and partial.exists() and metadata.exists()


def test_invalid_quarantine_expires_but_resume_without_final_survives(tmp_path,setup_downloads):
    target,partial,metadata=setup_downloads;target.unlink()
    invalid=partial.with_suffix('.part.invalid');invalid.write_bytes(b'bad')
    os.utime(invalid,(time.time()-8*86400,)*2)
    result=clean_download_remnants(tmp_path,Task(),apply=True)
    assert len(result['files'])==1 and not invalid.exists()
    assert partial.exists() and metadata.exists()


def test_aged_orphan_metadata_is_cleaned_after_verified_download(tmp_path,setup_downloads):
    target,partial,metadata=setup_downloads
    partial.unlink()
    result=clean_download_remnants(tmp_path,Task(),apply=True)
    assert result['files']==['models/model.pt.part.json'] and not metadata.exists() and target.exists()


def test_cancellation_does_not_remove_a_pending_download(tmp_path,setup_downloads):
    from geoforma.tasks import Cancelled
    target,partial,metadata=setup_downloads
    class CancelDuringCheck:
        def __init__(self):self.calls=0
        def check(self):
            self.calls+=1
            if self.calls==4:raise Cancelled('cancelled')
    with pytest.raises(Cancelled):clean_download_remnants(tmp_path,CancelDuringCheck(),apply=True)
    assert target.exists() and partial.exists() and metadata.exists()


def test_wheel_partial_is_preserved_during_runtime_install(tmp_path,monkeypatch):
    from geoforma import model_catalog,native_runtime
    payload=b'wheel';spec=dict(filename='runtime.whl',bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest())
    monkeypatch.setattr(model_catalog,'MODELS',())
    monkeypatch.setattr(native_runtime,'catalog',lambda:dict(profiles={'cpu':dict(wheels=[spec])}))
    folder=tmp_path/'runtime/native-v1/downloads';folder.mkdir(parents=True)
    (folder/'runtime.whl').write_bytes(payload);partial=folder/'runtime.whl.part';partial.write_bytes(b'part')
    os.utime(partial,(time.time()-172800,)*2)
    with try_resource_lock(folder.parent/'install.lock') as acquired:
        assert acquired and not clean_download_remnants(tmp_path,Task(),apply=True)['files']
    assert partial.exists()
    assert len(clean_download_remnants(tmp_path,Task(),apply=True)['files'])==1 and not partial.exists()


def test_incomplete_download_expires_only_after_thirty_days_of_inactivity(tmp_path,setup_downloads):
    target,partial,metadata=setup_downloads;target.unlink()
    old=time.time()-31*86400
    os.utime(partial,(old,old));os.utime(metadata,(old,old))
    with try_resource_lock(target.with_suffix('.download.lock')) as acquired:
        assert acquired and not clean_download_remnants(tmp_path,Task(),apply=True)['files']
    os.utime(metadata,None)
    assert not clean_download_remnants(tmp_path,Task(),apply=True)['files'] and partial.exists()
    os.utime(metadata,(old,old))
    result=clean_download_remnants(tmp_path,Task(),apply=True)
    assert set(result['files'])=={'models/model.pt.part','models/model.pt.part.json'}
    assert not partial.exists() and not metadata.exists() and (tmp_path/'models/other.pt.part').exists()


def test_old_orphan_metadata_and_known_atomic_temps_are_removed(tmp_path,setup_downloads):
    target,partial,metadata=setup_downloads;target.unlink();partial.unlink()
    files=[metadata,target.parent/'.model.pt.abcd1234.tmp',target.parent/'.model.pt.part.json.abcd1234.tmp',
           target.parent/'.model.download.json.abcd1234.tmp']
    for path in files:
        if path!=metadata:path.write_bytes(b'interrupted')
        os.utime(path,(time.time()-8*86400,)*2)
    unknown=target.parent/'.other.pt.abcd1234.tmp';unknown.write_bytes(b'user file');os.utime(unknown,(time.time()-8*86400,)*2)
    result=clean_download_remnants(tmp_path,Task(),apply=True)
    assert len(result['files'])==len(files) and all(not path.exists() for path in files)
    assert unknown.read_bytes()==b'user file'


@pytest.mark.parametrize('case',['installed','missing','wrong_hash','locked'])
def test_only_verified_old_wheel_backed_by_installed_runtime_is_removed(tmp_path,monkeypatch,case):
    from geoforma import model_catalog,native_runtime
    payload=b'official wheel';spec=dict(name='torch',version='1',filename='torch-test.whl',bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest())
    monkeypatch.setattr(model_catalog,'MODELS',())
    monkeypatch.setattr(native_runtime,'catalog',lambda:dict(profiles={'cpu':dict(wheels=[spec])}))
    root=tmp_path/'runtime/native-v1';downloads=root/'downloads';downloads.mkdir(parents=True)
    wheel=downloads/spec['filename'];wheel.write_bytes(b'wrong content!' if case=='wrong_hash' else payload)
    os.utime(wheel,(time.time()-31*86400,)*2)
    stage=root/('a'*32)
    if case!='missing':
        for relative in ('torch/__init__.py','torch/lib/torch_cpu.dll','torchvision/__init__.py'):
            path=stage/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'installed')
        state=dict(kind='geoforma-native-installed-v1',generation=stage.name,profile='cpu',
                   wheels=[{key:spec[key] for key in ('filename','sha256')}],probe=dict(ok=True,versions={'torch':'1'}))
        (stage/'installed.json').write_text(json.dumps(state))
    if case=='locked':
        with try_resource_lock(root/'install.lock') as acquired:
            assert acquired and not clean_download_remnants(tmp_path,Task(),apply=True)['files']
    else:clean_download_remnants(tmp_path,Task(),apply=True)
    assert wheel.exists()==(case!='installed')
    if stage.exists():assert (stage/'installed.json').exists() and (stage/'torch/lib/torch_cpu.dll').exists()


def test_runtime_stages_require_old_ownership_marker_and_unlocked_install(tmp_path):
    from geoforma.native_runtime import STAGE_MARKER,STAGE_MARKER_CONTENT
    root=tmp_path/'runtime/native-v1';root.mkdir(parents=True)
    def stage(letter,marked=True):
        folder=root/(letter*32);folder.mkdir();(folder/'torch').mkdir();(folder/'torch/data').write_bytes(b'partial')
        if marked:
            marker=folder/STAGE_MARKER;marker.write_text(STAGE_MARKER_CONTENT,encoding='utf-8');os.utime(marker,(time.time()-8*86400,)*2)
        return folder
    stale=stage('a');active=stage('b');unknown=stage('c',False);installed=stage('d');foreign=stage('e')
    (root/'current.json').write_text(json.dumps({'generation':active.name}))
    (installed/'installed.json').write_text('{}')
    (foreign/'notes.txt').write_text('user data')
    with try_resource_lock(root/'install.lock') as acquired:
        assert acquired and not clean_download_remnants(tmp_path,Task(),apply=True)['directories']
    result=clean_download_remnants(tmp_path,Task(),apply=True)
    assert result['directories']==['runtime/native-v1/'+stale.name] and not stale.exists()
    assert all(path.exists() for path in (active,unknown,installed,foreign))


def test_stage_cleanup_skips_unknown_current_state_and_junctions(tmp_path,monkeypatch):
    from geoforma.native_runtime import STAGE_MARKER,STAGE_MARKER_CONTENT
    root=tmp_path/'runtime/native-v1';stage=root/('f'*32);folder=stage/'torch';folder.mkdir(parents=True)
    marker=stage/STAGE_MARKER;marker.write_text(STAGE_MARKER_CONTENT,encoding='utf-8');os.utime(marker,(time.time()-8*86400,)*2)
    (folder/'data').write_bytes(b'partial');current=root/'current.json';current.write_text('invalid')
    assert not clean_download_remnants(tmp_path,Task(),apply=True)['directories'] and stage.exists()
    current.unlink();linked=folder/'linked';linked.mkdir();original=Path.is_junction
    monkeypatch.setattr(Path,'is_junction',lambda path:path==linked or original(path))
    result=clean_download_remnants(tmp_path,Task(),apply=True)
    assert not result['directories'] and stage.exists() and linked.exists() and marker.exists()


def test_failed_stage_cleanup_keeps_its_marker_for_retry(tmp_path,monkeypatch):
    from geoforma.native_runtime import STAGE_MARKER,STAGE_MARKER_CONTENT
    root=tmp_path/'runtime/native-v1';stage=root/('f'*32);folder=stage/'torch';folder.mkdir(parents=True)
    marker=stage/STAGE_MARKER;marker.write_text(STAGE_MARKER_CONTENT,encoding='utf-8');os.utime(marker,(time.time()-8*86400,)*2)
    data=folder/'data';data.write_bytes(b'partial');original=Path.unlink
    def blocked(path,*args,**kwargs):
        if path==data:raise PermissionError('busy')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'unlink',blocked)
    result=clean_download_remnants(tmp_path,Task(),apply=True)
    assert not result['directories'] and marker.exists() and data.exists()
    monkeypatch.setattr(Path,'unlink',original)
    assert clean_download_remnants(tmp_path,Task(),apply=True)['directories'] and not stage.exists()


def test_cancelled_stage_cleanup_keeps_its_marker_for_retry(tmp_path,monkeypatch):
    from geoforma.native_runtime import STAGE_MARKER,STAGE_MARKER_CONTENT
    from geoforma.tasks import Cancelled
    root=tmp_path/'runtime/native-v1';stage=root/('f'*32);folder=stage/'torch';folder.mkdir(parents=True)
    marker=stage/STAGE_MARKER;marker.write_text(STAGE_MARKER_CONTENT,encoding='utf-8');os.utime(marker,(time.time()-8*86400,)*2)
    files=[folder/'a',folder/'b']
    for path in files:path.write_bytes(b'partial')
    class CancelAfterRemoval:
        cancelled=False
        def check(self):
            if self.cancelled:raise Cancelled('cancelled')
    task=CancelAfterRemoval();original=Path.unlink
    def remove_then_cancel(path,*args,**kwargs):
        result=original(path,*args,**kwargs)
        if path in files:task.cancelled=True
        return result
    monkeypatch.setattr(Path,'unlink',remove_then_cancel)
    with pytest.raises(Cancelled):clean_download_remnants(tmp_path,task,apply=True)
    assert marker.exists() and any(path.exists() for path in files)
    monkeypatch.setattr(Path,'unlink',original)
    assert clean_download_remnants(tmp_path,Task(),apply=True)['directories'] and not stage.exists()


def test_housekeeping_runs_in_background_and_stops_on_close(workbench,monkeypatch):
    import threading
    from geoforma import housekeeping
    w,app,wait,errors=workbench;started=threading.Event()
    def slow(root,task,apply=False):
        started.set()
        while True:task.check();threading.Event().wait(.005)
    monkeypatch.setattr(housekeeping,'clean_download_remnants',slow)
    w.start_background_cleanup();until(app,started.is_set)
    assert w.task is None and w.project_actions['open'].isEnabled()
    w.dirty=False;w.close();until(app,lambda:w.housekeeping_task is None)
    until(app,lambda:w.shutdown_complete)
    assert not errors
