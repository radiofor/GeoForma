import subprocess
import sys

import pytest


def test_resource_lease_excludes_other_processes_and_releases(tmp_path):
    from geoforma.session_guard import ResourceLease
    script=("from geoforma.session_guard import ResourceLease\n"
            "import sys\nlease=ResourceLease()\n"
            "try:\n lease.ensure(sys.argv[1]); print('acquired')\n"
            "except ValueError: print('busy')\n"
            "finally: lease.close()\n")
    def attempt():
        return subprocess.run([sys.executable,'-c',script,str(tmp_path)],capture_output=True,text=True,check=True,
                              creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)).stdout.strip()
    lease=ResourceLease()
    try:
        lease.ensure(tmp_path)
        assert attempt()=='busy'
    finally:lease.close()
    assert attempt()=='acquired'


def test_failed_transition_keeps_original_lease(tmp_path):
    from geoforma.session_guard import ResourceLease
    old=tmp_path/'old';new=tmp_path/'new';old.mkdir();new.mkdir()
    first=ResourceLease();second=ResourceLease()
    try:
        first.ensure(old)
        with pytest.raises(ValueError):
            with first.transition(new):raise ValueError('failed to save')
        assert first.root==old.resolve()
        with pytest.raises(ValueError,match='另一个'):
            second.ensure(old)
        second.ensure(new)
    finally:first.close();second.close()


def test_busy_destination_keeps_original_lease(tmp_path):
    from geoforma.session_guard import ResourceLease
    old=tmp_path/'old';new=tmp_path/'new';old.mkdir();new.mkdir()
    first=ResourceLease();second=ResourceLease()
    try:
        first.ensure(old);second.ensure(new)
        with pytest.raises(ValueError,match='另一个'):
            with first.transition(new):pass
        assert first.root==old.resolve()
    finally:first.close();second.close()


def test_cleanup_command_cannot_clear_another_session_cache(tmp_path,monkeypatch):
    import json,os
    from geoforma.resource_location import set_resource_parent
    from geoforma.session_guard import ResourceLease
    first=tmp_path/'profile1';second=tmp_path/'profile2';parent=tmp_path/'volume'
    first.mkdir();second.mkdir();parent.mkdir()
    monkeypatch.setenv('GEOFORMA_DATA_DIR',str(first));root=set_resource_parent(parent)
    monkeypatch.setenv('GEOFORMA_DATA_DIR',str(second));assert set_resource_parent(parent)==root
    folder=root/'cache'/'features';folder.mkdir(parents=True);feature=folder/('a'*64+'.pt');feature.write_bytes(b'keep')
    report=tmp_path/'report.json';env=dict(os.environ,QT_QPA_PLATFORM='offscreen')
    lease=ResourceLease()
    try:
        lease.ensure(root)
        process=subprocess.run([sys.executable,'main.py','--runtime-command','cleanup-cache','--output',str(report)],
                               env=env,capture_output=True,text=True,timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        assert process.returncode==1 and not json.loads(report.read_text(encoding='utf-8'))['ok']
        assert feature.read_bytes()==b'keep'
    finally:lease.close()
