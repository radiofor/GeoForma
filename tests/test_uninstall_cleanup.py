from pathlib import Path
import base64,hashlib,json
import pytest

from geoforma.uninstall_cleanup import clean_known_data, cleanup_selected


def test_selected_cleanup_preserves_unknown_data_and_saved_projects(tmp_path):
    from geoforma.model_catalog import MODELS
    model=tmp_path/'models'/MODELS[0]['file'];model.parent.mkdir()
    model.write_bytes(b'weights')
    other=model.parent/'private.pt';other.write_bytes(b'private')
    recovery=tmp_path/'recovery'/'untitled.gfm';recovery.parent.mkdir();recovery.write_text('work')
    project=tmp_path/'user-project.gfm';project.write_text('project')
    log=tmp_path/'errors.log';log.write_text('errors')
    clean_known_data(tmp_path,models=True,caches=True)
    assert not model.exists() and not log.exists()
    assert other.exists() and recovery.exists() and project.exists()
    clean_known_data(tmp_path,recovery=True)
    assert not recovery.exists() and other.exists() and project.exists()


def test_cleanup_refuses_linked_directory(tmp_path):
    target=tmp_path/'outside';target.mkdir()
    link=tmp_path/'data'/'models';link.parent.mkdir()
    try:link.symlink_to(target, target_is_directory=True)
    except OSError:pytest.skip('当前账户无法创建目录链接')
    with pytest.raises(ValueError):clean_known_data(link.parent,models=True)


def test_cleanup_refuses_junction_component(tmp_path, monkeypatch):
    root=tmp_path/'data';root.mkdir();folder=root/'models';folder.mkdir()
    original=Path.is_junction
    monkeypatch.setattr(Path,'is_junction',lambda path:path==folder or original(path))
    with pytest.raises(ValueError,match='链接'):
        clean_known_data(root,models=True)


def test_cleanup_rejects_unknown_user_before_touching_data(tmp_path, monkeypatch):
    from geoforma import uninstall_identity,uninstall_cleanup
    root=tmp_path/'data';root.mkdir();log=root/'errors.log';log.write_text('keep')
    monkeypatch.setattr(uninstall_cleanup,'_local_data_root',lambda:root)
    monkeypatch.setattr(uninstall_identity,'current_user_owns_desktop',lambda:False)
    with pytest.raises(ValueError,match='无法确认'):
        cleanup_selected(1,root)
    assert log.read_text()=='keep'


def test_cleanup_refuses_pending_migration(tmp_path, monkeypatch):
    from geoforma import uninstall_identity,uninstall_cleanup
    root=tmp_path/'data';root.mkdir();log=root/'errors.log';log.write_text('keep')
    monkeypatch.setattr(uninstall_cleanup,'_local_data_root',lambda:root)
    monkeypatch.setattr(uninstall_identity,'current_user_owns_desktop',lambda:True)
    (root/'resource-migration.json').write_text('{}')
    with pytest.raises(ValueError,match='迁移'):
        cleanup_selected(1,root)
    assert log.read_text()=='keep'


def test_cleanup_ignores_environment_data_override(tmp_path,monkeypatch):
    from geoforma import uninstall_identity,uninstall_cleanup,resource_location
    root=tmp_path/'real';root.mkdir();outside=tmp_path/'other';outside.mkdir()
    (root/'errors.log').write_text('remove');(outside/'errors.log').write_text('keep')
    monkeypatch.setattr(uninstall_cleanup,'_local_data_root',lambda:root)
    monkeypatch.setattr(uninstall_identity,'current_user_owns_desktop',lambda:True)
    monkeypatch.setattr(resource_location,'require_resource_dir',lambda data:resource_location.default_resource_dir(data))
    (root/'cache').mkdir();(root/'cache'/'active-project.json').write_text('{}')
    monkeypatch.setenv('GEOFORMA_DATA_DIR',str(outside))
    cleanup_selected(1,root)
    assert not (root/'errors.log').exists() and (outside/'errors.log').read_text()=='keep'


def test_changed_resource_location_is_rejected_after_lock(tmp_path,monkeypatch):
    from geoforma import uninstall_identity,uninstall_cleanup,resource_location,session_guard
    data=tmp_path/'data';data.mkdir();current=tmp_path/'current';current.mkdir()
    confirmed=tmp_path/'confirmed';confirmed.mkdir()
    (current/'errors.log').write_text('keep')
    monkeypatch.setattr(uninstall_cleanup,'_local_data_root',lambda:data)
    monkeypatch.setattr(uninstall_identity,'current_user_owns_desktop',lambda:True)
    def resolved(_):
        session_guard.guard_resource(current)
        return current
    monkeypatch.setattr(resource_location,'require_resource_dir',resolved)
    with pytest.raises(ValueError,match='资源目录已更改'):
        cleanup_selected(1,confirmed)
    assert (current/'errors.log').read_text()=='keep'


def test_resource_cleanup_requires_explicit_confirmation(tmp_path,monkeypatch):
    from geoforma import uninstall_identity
    monkeypatch.setattr(uninstall_identity,'current_user_owns_desktop',lambda:True)
    with pytest.raises(ValueError,match='无法确认用户选择'):
        cleanup_selected(1)


def test_runtime_cleanup_removes_verified_record_files_preserving_unknown(tmp_path,monkeypatch):
    from geoforma import uninstall_cleanup
    from geoforma.uninstall_cleanup import clean_installed_runtimes
    runtime=tmp_path/'runtime'/'native-v1';site=runtime/('a'*32);site.mkdir(parents=True)
    marker=site/'installed.json';marker.write_text(json.dumps({'wheels':[{'filename':'torch-1.0-test.whl'}]}))
    package=site/'torch';package.mkdir();owned=package/'a.py';owned.write_bytes(b'verified')
    unknown=package/'user.txt';unknown.write_text('keep')
    info=site/'torch-1.0.dist-info';info.mkdir()
    digest=base64.urlsafe_b64encode(hashlib.sha256(b'verified').digest()).decode().rstrip('=')
    (info/'RECORD').write_text(f'torch/a.py,sha256={digest},8\ntorch-1.0.dist-info/RECORD,,\n')
    monkeypatch.setattr(uninstall_cleanup,'_owned_runtime',lambda state,generation:True)
    removed,skipped=clean_installed_runtimes(tmp_path)
    assert not owned.exists() and unknown.read_text()=='keep' and marker.exists()
    assert str(owned) in removed and str(unknown) in skipped
    unknown.unlink()
    removed,skipped=clean_installed_runtimes(tmp_path)
    assert not skipped and not site.exists()


def test_runtime_owner_validation_survives_missing_package_files():
    from geoforma.native_runtime import profile
    from geoforma.uninstall_cleanup import _owned_runtime
    spec=profile('cpu');generation='b'*32
    state={'kind':'geoforma-native-installed-v1','generation':generation,'profile':'cpu',
           'wheels':[{k:w[k] for k in ('filename','sha256')} for w in spec['wheels']],
           'probe':{'ok':True,'versions':{w['name']:w['version'] for w in spec['wheels']}}}
    assert _owned_runtime(state,generation)
    state['wheels'][0]['sha256']='untrusted'
    assert not _owned_runtime(state,generation)


def test_metadata_is_retained_if_unknown_data_remains(tmp_path):
    from geoforma.uninstall_cleanup import _has_remaining_content
    root=tmp_path/'resources';root.mkdir();data=tmp_path/'data';data.mkdir()
    (root/'.geoforma-resources').write_text('marker')
    (data/'resource-location.json').write_text('{}')
    assert not _has_remaining_content(root,data)
    assert not _has_remaining_content(data,data)
    (root/'private.txt').write_text('keep')
    assert _has_remaining_content(root,data)


def test_unreadable_or_nested_marker_keeps_metadata(tmp_path,monkeypatch):
    from geoforma import uninstall_cleanup
    root=tmp_path/'resources';root.mkdir();nested=root/'private';nested.mkdir()
    (nested/'.geoforma-resources').write_text('user data')
    assert uninstall_cleanup._has_remaining_content(root,tmp_path/'data')
    def inaccessible(*args,**kwargs):
        raise PermissionError('denied')
    monkeypatch.setattr(uninstall_cleanup.os,'walk',inaccessible)
    assert uninstall_cleanup._has_remaining_content(root,tmp_path/'data')
