import json
import subprocess
import sys
import pytest


def test_new_default_uses_resources_folder_but_existing_cache_stays_in_place(tmp_path,monkeypatch):
    from geoforma.resource_location import current_resource_dir,require_resource_dir
    monkeypatch.delenv('GEOFORMA_DATA_DIR',raising=False)
    fresh=tmp_path/'fresh'/'GeoForma';fresh.mkdir(parents=True)
    expected=fresh.parent/'GeoForma-Resources'
    assert current_resource_dir(fresh)==expected
    assert require_resource_dir(fresh)==expected
    assert (expected/'.geoforma-resources').is_file()
    legacy=tmp_path/'legacy'/'GeoForma';(legacy/'cache').mkdir(parents=True)
    (legacy/'cache'/'active-project.json').write_text('{}')
    assert current_resource_dir(legacy)==legacy
    assert require_resource_dir(legacy)==legacy


def test_cache_switch_preserves_original_and_reuses_when_switched_back(tmp_path,monkeypatch):
    from geoforma.resource_location import set_resource_parent,reset_resource_dir,require_resource_dir
    from geoforma.project_cache import activate_project_cache
    monkeypatch.setenv('GEOFORMA_DATA_DIR',str(tmp_path/'app-data'))
    original=require_resource_dir();owner='a'*32
    first=activate_project_cache(original,owner)
    original_file=original/'cache'/'features'/('b'*64+'.pt')
    original_file.parent.mkdir(parents=True,exist_ok=True);original_file.write_bytes(b'ready')
    parent=tmp_path/'other';parent.mkdir()
    selected=set_resource_parent(parent)
    second=activate_project_cache(require_resource_dir(),owner)
    assert selected!=original and second['revision']!=first['revision']
    assert original_file.read_bytes()==b'ready'
    reset_resource_dir()
    recovered=activate_project_cache(require_resource_dir(),owner)
    assert recovered['cleared'] is False and recovered['revision']==first['revision']
    assert original_file.read_bytes()==b'ready'


def test_recovery_can_find_legacy_data_after_location_change(tmp_path):
    from geoforma.recovery import recovery_target
    class Settings:
        def value(self,*args):return ''
    legacy=tmp_path/'legacy';selected=tmp_path/'selected'
    (legacy/'recovery').mkdir(parents=True)
    path=legacy/'recovery'/'untitled.geoforma.json';path.write_text('{}')
    assert recovery_target(Settings(),selected,legacy)==path
    newer=selected/'recovery'/'untitled.geoforma.json';newer.parent.mkdir(parents=True);newer.write_text('{}')
    import os
    os.utime(path,ns=(100,100));os.utime(newer,ns=(200,200))
    class RememberOld:
        def value(self,key,default=''):return str(path) if key=='recovery/last_work' else ''
    assert recovery_target(RememberOld(),selected,legacy)==newer


def test_error_log_is_bounded_and_preserves_unrelated_files(tmp_path):
    from geoforma.logging_limits import append_error,MAX_LOG_BYTES
    other=tmp_path/'other.log';other.write_text('keep')
    append_error(tmp_path,'a'*MAX_LOG_BYTES)
    append_error(tmp_path,'new')
    assert (tmp_path/'errors.log').read_text(encoding='utf-8')=='new\n'
    assert other.read_text()=='keep'


def test_selected_resource_root_is_persistent_and_separate_from_project_data(tmp_path,monkeypatch):
    from geoforma.domain import data_dir
    from geoforma.resource_location import current_resource_dir,set_resource_parent,reset_resource_dir
    from geoforma.native_runtime import runtime_root
    from geoforma.weights import default_checkpoint
    monkeypatch.setenv('GEOFORMA_DATA_DIR',str(tmp_path/'app-data'))
    root=data_dir();recovery=root/'recovery';recovery.mkdir();(recovery/'saved').write_text('keep')
    old=root/'models';old.mkdir();(old/'existing').write_text('keep')
    parent=tmp_path/'disk';parent.mkdir()
    target=set_resource_parent(parent)
    assert target==parent/'GeoForma-Resources'
    assert current_resource_dir()==target
    child=subprocess.check_output([sys.executable,'-c','from geoforma.resource_location import current_resource_dir; print(current_resource_dir())'],text=True).strip()
    assert child==str(target)
    assert runtime_root()==target/'runtime'/'native-v1'
    assert default_checkpoint('small','sam2.1').parent==target/'models'
    assert (recovery/'saved').read_text()=='keep' and (old/'existing').read_text()=='keep'
    assert reset_resource_dir()==root and current_resource_dir()==root


def test_existing_unmanaged_directory_is_not_adopted_or_modified(tmp_path,monkeypatch):
    from geoforma.resource_location import set_resource_parent,current_resource_dir
    monkeypatch.setenv('GEOFORMA_DATA_DIR',str(tmp_path/'app-data'))
    folder=tmp_path/'GeoForma-Resources';folder.mkdir();(folder/'user-file').write_text('keep')
    with pytest.raises(ValueError,match='其他文件'):set_resource_parent(tmp_path)
    assert (folder/'user-file').read_text()=='keep'
    assert current_resource_dir()==tmp_path/'app-data'


def test_bad_saved_location_never_falls_back_silently(tmp_path,monkeypatch):
    from geoforma.resource_location import current_resource_dir,require_resource_dir
    root=tmp_path/'app-data';root.mkdir();monkeypatch.setenv('GEOFORMA_DATA_DIR',str(root))
    (root/'resource-location.json').write_text(json.dumps({'kind':'geoforma-resource-location-v1','path':str(tmp_path/'GeoForma-Resources')}))
    assert current_resource_dir()==tmp_path/'GeoForma-Resources'
    with pytest.raises(ValueError,match='不可访问'):require_resource_dir()


def test_corrupt_location_does_not_prevent_project_creation_or_reuse_default(tmp_path,monkeypatch):
    from geoforma.domain import new_project
    from geoforma.resource_location import current_resource_dir
    root=tmp_path/'app-data';root.mkdir();monkeypatch.setenv('GEOFORMA_DATA_DIR',str(root))
    (root/'resource-location.json').write_text('{broken',encoding='utf-8')
    project=new_project()
    assert '.unavailable-resource-location' in project['model']['checkpoint']
    with pytest.raises(ValueError):current_resource_dir()
