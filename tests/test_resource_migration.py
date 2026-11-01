from types import SimpleNamespace
import pytest
import os
import subprocess
import sys


class Task:
    def __init__(self):self.signals=SimpleNamespace(progress=SimpleNamespace(emit=lambda *a:None))
    def check(self):pass


def test_progress_is_throttled_but_always_checks_cancellation(monkeypatch):
    from geoforma import resource_migration
    calls=[];checks=[]
    task=SimpleNamespace(check=lambda:checks.append(1),signals=SimpleNamespace(progress=SimpleNamespace(emit=lambda *args:calls.append(args))))
    monkeypatch.setattr(resource_migration.time,'monotonic',lambda:1.0)
    for current in [0,0,1,2,3,100]:resource_migration._progress(task,'复制',current,100)
    resource_migration._progress(task,'清理',0,2)
    assert len(checks)==7 and calls==[(0,100,'复制'),(100,100,'复制'),(0,2,'清理')]


def test_migration_moves_verified_managed_files_and_keeps_unknown(tmp_path,monkeypatch):
    from geoforma.resource_migration import migrate_resources,pending_migration
    from geoforma.resource_location import require_resource_dir
    from geoforma.session_guard import resource_session
    root=tmp_path/'original';root.mkdir();monkeypatch.setenv('GEOFORMA_DATA_DIR',str(root))
    (root/'cache/features').mkdir(parents=True);feature=root/'cache/features'/('a'*64+'.pt');feature.write_bytes(b'feature')
    (root/'cache/active-project.json').write_text('{"owner":"a"}')
    unknown=root/'personal.txt';unknown.write_text('keep')
    parent=tmp_path/'disk';parent.mkdir()
    with resource_session():
        result=migrate_resources(parent,Task());target=parent/'GeoForma-Resources'
        assert require_resource_dir()==target and result['destination']==str(target)
    assert (target/'cache/features'/feature.name).read_bytes()==b'feature'
    assert not feature.exists() and unknown.read_text()=='keep' and pending_migration() is None


def test_interrupted_copy_resumes_without_losing_source(tmp_path,monkeypatch):
    from geoforma.resource_migration import migrate_resources,pending_migration,resume_migration
    from geoforma.session_guard import resource_session
    root=tmp_path/'original';root.mkdir();monkeypatch.setenv('GEOFORMA_DATA_DIR',str(root))
    (root/'cache/features').mkdir(parents=True);feature=root/'cache/features'/('b'*64+'.pt');feature.write_bytes(b'feature')
    parent=tmp_path/'disk';parent.mkdir()
    task=Task()
    def cancel(current,total,stage):
        if stage=='复制并校验资源':raise RuntimeError('interrupted')
    task.signals.progress.emit=cancel
    with resource_session():
        with pytest.raises(RuntimeError,match='interrupted'):migrate_resources(parent,task)
        assert pending_migration() and feature.exists()
        resume_migration(Task())
    assert not feature.exists() and (parent/'GeoForma-Resources/cache/features'/feature.name).read_bytes()==b'feature'


def test_interrupted_after_switch_keeps_journal_and_resumes(tmp_path,monkeypatch):
    from geoforma.resource_migration import migrate_resources,pending_migration,resume_migration
    from geoforma.resource_location import current_resource_dir
    from geoforma.session_guard import resource_session
    root=tmp_path/'original';root.mkdir();monkeypatch.setenv('GEOFORMA_DATA_DIR',str(root))
    (root/'cache/features').mkdir(parents=True);feature=root/'cache/features'/('c'*64+'.pt');feature.write_bytes(b'feature')
    parent=tmp_path/'disk';parent.mkdir();task=Task()
    def cancel(current,total,stage):
        if stage=='清理已迁移资源':raise RuntimeError('interrupted')
    task.signals.progress.emit=cancel
    with resource_session():
        with pytest.raises(RuntimeError,match='interrupted'):migrate_resources(parent,task)
        assert current_resource_dir()==parent/'GeoForma-Resources' and feature.exists() and pending_migration()
        resume_migration(Task())
    assert not feature.exists() and pending_migration() is None


@pytest.mark.parametrize('phase',['copy','after_config','partial_cleanup'])
def test_process_termination_can_resume_without_losing_files(tmp_path,monkeypatch,phase):
    from geoforma.resource_migration import pending_migration,resume_migration
    from geoforma.session_guard import resource_session
    root=tmp_path/'original';root.mkdir();monkeypatch.setenv('GEOFORMA_DATA_DIR',str(root))
    folder=root/'cache/features';folder.mkdir(parents=True)
    expected={('a'*64+'.pt'):b'first',('b'*64+'.pt'):b'second'}
    for name,content in expected.items():(folder/name).write_bytes(content)
    parent=tmp_path/'disk';parent.mkdir()
    script='''
import os,sys
from types import SimpleNamespace
from pathlib import Path
import geoforma.resource_migration as migration
from geoforma.session_guard import resource_session
phase=sys.argv[2]
original=migration.atomic_json
original_unlink=Path.unlink
def unlink(path,*args,**kwargs):
    result=original_unlink(path,*args,**kwargs)
    if phase=='partial_cleanup' and path.name=='a'*64+'.pt' and 'original' in path.parts:os._exit(77)
    return result
Path.unlink=unlink
def save(path,value,**kwargs):
    original(path,value,**kwargs)
    if phase=='after_config' and path.name=='resource-location.json':os._exit(77)
migration.atomic_json=save
def emit(value,total,stage):
    if phase=='copy' and stage=='复制并校验资源':os._exit(77)
task=SimpleNamespace(check=lambda:None,signals=SimpleNamespace(progress=SimpleNamespace(emit=emit)))
with resource_session():migration.migrate_resources(sys.argv[1],task)
'''
    result=subprocess.run([sys.executable,'-c',script,str(parent),phase],env=os.environ.copy(),timeout=60)
    assert result.returncode==77 and pending_migration()
    target=parent/'GeoForma-Resources/cache/features'
    for name,content in expected.items():
        assert (folder/name).exists() or (target/name).read_bytes()==content
    with resource_session():resume_migration(Task())
    assert pending_migration() is None
    for name,content in expected.items():assert not (folder/name).exists() and (target/name).read_bytes()==content


def test_conflicting_target_never_overwrites_or_removes_source(tmp_path,monkeypatch):
    from geoforma.resource_migration import migrate_resources
    from geoforma.resource_location import prepare_resource_parent
    from geoforma.session_guard import resource_session
    root=tmp_path/'original';root.mkdir();monkeypatch.setenv('GEOFORMA_DATA_DIR',str(root))
    (root/'cache/features').mkdir(parents=True);name='d'*64+'.pt';(root/'cache/features'/name).write_bytes(b'original')
    parent=tmp_path/'disk';parent.mkdir();target=prepare_resource_parent(parent)
    (target/'cache/features').mkdir(parents=True);(target/'cache/features'/name).write_bytes(b'existing')
    with resource_session(),pytest.raises(ValueError,match='已有数据'):migrate_resources(parent,Task())
    assert (root/'cache/features'/name).read_bytes()==b'original' and (target/'cache/features'/name).read_bytes()==b'existing'


def test_tampered_journal_cannot_delete_unmanaged_file(tmp_path,monkeypatch):
    import hashlib
    from geoforma.atomic_io import atomic_json
    from geoforma.resource_location import prepare_resource_parent
    from geoforma.resource_migration import resume_migration
    from geoforma.session_guard import resource_session
    root=tmp_path/'original';root.mkdir();monkeypatch.setenv('GEOFORMA_DATA_DIR',str(root))
    secret=root/'private.txt';secret.write_bytes(b'keep')
    parent=tmp_path/'disk';parent.mkdir();target=prepare_resource_parent(parent)
    (target/'private.txt').write_bytes(b'keep')
    atomic_json(root/'resource-migration.json',{'kind':'geoforma-resource-migration-v1','phase':'copy','source':str(root),'destination':str(target),'files':[{'path':'private.txt','bytes':4,'sha256':hashlib.sha256(b'keep').hexdigest()}]})
    with resource_session(),pytest.raises(ValueError,match='记录无效'):resume_migration(Task())
    assert secret.read_bytes()==b'keep'


def test_migrate_back_to_legacy_default_persists_across_restart(tmp_path,monkeypatch):
    from geoforma.resource_migration import migrate_resources,migrate_to_default
    from geoforma.resource_location import current_resource_dir
    from geoforma.session_guard import resource_session
    root=tmp_path/'original';root.mkdir();monkeypatch.setenv('GEOFORMA_DATA_DIR',str(root))
    (root/'cache/features').mkdir(parents=True);name='e'*64+'.pt';(root/'cache/features'/name).write_bytes(b'feature')
    parent=tmp_path/'disk';parent.mkdir()
    with resource_session():
        migrate_resources(parent,Task());migrate_to_default(Task())
        assert current_resource_dir()==root
    result=subprocess.check_output([sys.executable,'-c','from geoforma.resource_location import current_resource_dir; print(current_resource_dir())'],text=True).strip()
    assert result==str(root) and (root/'cache/features'/name).read_bytes()==b'feature'
