import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication,QDialog
from shiboken6 import isValid
from geoforma.atomic_io import read_json
from geoforma.domain import new_project
from geoforma.project_validation import validate_project
from geoforma.reference_catalog import ReferenceLookup,merge_references
from geoforma.release_artifacts import collect_licenses,release_inventory
from geoforma.tasks import Task
from geoforma.ui.modal import dialog_result
from tools.clean_generated import clean
from test_workbench import workbench,fake_image


@pytest.mark.parametrize('text',['{"value":1,"value":2}','{"value":1e10000}','{"nested":{"id":1,"id":2}}'])
def test_json_rejects_ambiguous_or_overflowed_input(tmp_path,text):
    path=tmp_path/'invalid.json';path.write_text(text)
    with pytest.raises(ValueError):read_json(path)


@pytest.mark.parametrize('classes',[[dict(id=0,name='zero')],[dict(id=65535,name='nodata')],[dict(id=True,name='bool')],
    [dict(id=1,name=' ')],[dict(id=1,name='Lake'),dict(id=2,name=' lake ')],['invalid']])
def test_project_classes_share_editor_contract(classes):
    project=new_project();project['classes']=classes
    with pytest.raises(ValueError):validate_project(project)


def test_unknown_label_class_and_invalid_schema_are_rejected():
    from shapely.geometry import box,mapping
    project=new_project();project['schema']=True
    with pytest.raises(ValueError):validate_project(project)
    project['schema']=1;image=fake_image('main');project['images']=[image]
    project['labels']=[dict(id='label',image_id='main',status='confirmed',class_id=99,geometry=mapping(box(0,0,1,1)))]
    with pytest.raises(ValueError,match='类别'):validate_project(project)


def test_import_limits_apply_across_the_whole_selection(tmp_path,monkeypatch):
    import geoforma.image_list as lists
    monkeypatch.setattr(lists,'MAX_IMAGES',2)
    plan=lists.plan_import(['a.tif','a.tif','b.tif','c.tif','d.tif'])
    assert len(plan.entries)==2 and plan.duplicates==1 and len(plan.errors)==1
    document='<VRTDataset><VRTRasterBand><SimpleSource><SourceFilename relativeToVRT="1">a.tif</SourceFilename></SimpleSource></VRTRasterBand></VRTDataset>'
    paths=[]
    for name in ('one.vrt','two.vrt'):
        path=tmp_path/name;path.write_text(document);paths.append(path)
    monkeypatch.setattr(lists,'MAX_TOTAL_VRT_BYTES',paths[0].stat().st_size)
    plan=lists.plan_import(paths);assert len(plan.entries)==1 and '64 MiB' in plan.errors[0]


def test_reference_reimport_keeps_order_caption_current_frame_and_canonical_buttons(workbench):
    w,app,wait,errors=workbench;image=fake_image('main','tile.tif');w.project['images']=[image]
    references=[dict(image,path='NDWI/tile.tif',group='NDWI'),dict(image,path='VV/tile.tif',group='VV')]
    w.project['references']=references;w.refresh_images();w.images.setCurrentRow(0)
    w.switch_reference(references[0]);w.visible_reference=references[0];w.reference_transition_pending=False
    generation=w.render_generation;button=w.reference_buttons[('ndwi','NDWI/tile.tif')];render=[];w.request_render=lambda *args:render.append(args)
    replacement=dict(references[0],group='ndwi',reference_origin={'kind':'list','name':'new.yaml'})
    merged=merge_references(references,[replacement]);w.replace_references(merged)
    assert [record['group'] for record in merged]==['NDWI','VV']
    assert w.display_reference is merged[0] and w.visible_reference is merged[0]
    assert w.reference_buttons[('ndwi','NDWI/tile.tif')] is button and button.isChecked()
    assert 'new.yaml' in button.toolTip() and not render and w.render_generation==generation
    w.switch_reference(dict(merged[0]));assert w.display_reference is merged[0] and not render
    changed=merge_references(merged,[dict(merged[0],fingerprint='new-pixels')]);w.replace_references(changed)
    assert render==[(True,)] and w.display_reference is changed[0] and w.render_generation==generation+1
    assert not errors and references[0]['group']=='NDWI'


def test_reference_lookup_reuses_index_and_invalidates_when_catalog_replaced():
    lookup=ReferenceLookup();records=[dict(path=f'{i}.tif',group='NDWI') for i in range(10000)]
    image={'path':'9999.tif'};assert lookup.for_image(records,image)==(records[-1],)
    index=lookup.by_stem
    for _ in range(50):assert lookup.for_image(records,image)==(records[-1],)
    assert lookup.by_stem is index
    replacement=[*records[:-1],dict(records[-1],group='VV')]
    assert lookup.for_image(replacement,image)==(replacement[-1],) and lookup.by_stem is not index


def test_release_inventory_is_repeatable_without_hashing_its_own_previous_version(tmp_path):
    (tmp_path/'GeoForma.exe').write_bytes(b'program');before=release_inventory(tmp_path)
    (tmp_path/'release-manifest.json').write_text(json.dumps(before))
    assert release_inventory(tmp_path)==before and before[0]['path']=='GeoForma.exe'


def test_license_collection_preserves_distinct_licenses_and_excludes_executable_files(tmp_path):
    source=tmp_path/'source';files=['pkg.dist-info/licenses/one/LICENSE.txt','pkg.dist-info/licenses/two/LICENSE.txt',
        'pkg/licenses/_spdx.py','pkg/licenses/__pycache__/cache.pyc','pkg.dist-info/licenses/AUTHORS']
    for name in files:path=source/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(name)
    dist=SimpleNamespace(metadata={'Name':'pkg'},version='1',files=map(Path,files),locate_file=lambda file:source/file)
    target=tmp_path/'licenses';collect_licenses([dist],target)
    assert sorted(file.name for file in target.rglob('*') if file.is_file())==['AUTHORS','LICENSE.txt','LICENSE.txt']
    assert len({file.read_text() for file in target.rglob('LICENSE.txt')})==2


def test_transient_dialog_is_released_after_its_pending_task_callbacks(monkeypatch):
    app=QApplication.instance() or QApplication([]);dialog=QDialog();task=Task(lambda task:None)
    monkeypatch.setattr(dialog,'exec',lambda:0)
    assert dialog_result(dialog,owner=SimpleNamespace(task=task))==(False,None)
    app.sendPostedEvents(None,QEvent.Type.DeferredDelete);assert isValid(dialog)
    task.signals.finished.emit();app.sendPostedEvents(None,QEvent.Type.DeferredDelete);assert not isValid(dialog)


def test_generated_cleanup_preserves_environment_releases_and_user_data(tmp_path):
    for name in ('geoforma/__pycache__/module.pyc','tests/__pycache__/test.pyc','environment/__pycache__/keep.pyc',
                 'release/models/keep.pth','build/report.json','examples/project.json'):
        path=tmp_path/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('keep')
    report=clean(tmp_path);assert report['files']==2 and (tmp_path/'geoforma/__pycache__').exists()
    clean(tmp_path,True)
    assert not (tmp_path/'geoforma/__pycache__').exists() and (tmp_path/'environment/__pycache__/keep.pyc').exists()
    assert all((tmp_path/name).exists() for name in ('release/models/keep.pth','build/report.json','examples/project.json'))


def test_release_gate_blocks_affected_runtime_and_accepts_fixed_version_floors():
    from geoforma.runtime_profile import SECURITY_MINIMUMS,require_release_security
    require_release_security(dict(SECURITY_MINIMUMS))
    with pytest.raises(ValueError,match='torch'):require_release_security({**SECURITY_MINIMUMS,'torch':'2.10.0+cu128'})
    with pytest.raises(ValueError,match='Pillow'):require_release_security({**SECURITY_MINIMUMS,'Pillow':'12.3.0'})


def test_weight_download_rejects_insecure_initial_and_redirect_urls():
    from urllib.request import Request
    from urllib.error import HTTPError
    from geoforma.network import HTTPSRedirectHandler,open_https
    with pytest.raises(ValueError):open_https('http://example.com/weights.pt')
    with pytest.raises(HTTPError):HTTPSRedirectHandler().redirect_request(Request('https://example.com/weights.pt'),None,302,'Found',{},'http://example.com/weights.pt')


def test_unvalidated_runtime_profile_does_not_activate(tmp_path):
    from geoforma.runtime_profile import activate_security_profile
    folder=tmp_path/'environment/security-runtime';folder.mkdir(parents=True)
    assert activate_security_profile(tmp_path) is False
    (folder/'geoforma-profile.json').write_text(json.dumps({'validated':False}))
    with pytest.raises(RuntimeError):activate_security_profile(tmp_path)


def test_validated_profile_activates_only_owned_path_and_matching_versions(tmp_path,monkeypatch):
    import sys,os,importlib.metadata
    from geoforma.runtime_profile import activate_security_profile,SECURITY_MINIMUMS
    folder=tmp_path/'environment/security-runtime';folder.mkdir(parents=True)
    (folder/'geoforma-profile.json').write_text(json.dumps({'validated':True,'python':sys.implementation.cache_tag,'platform':sys.platform,'versions':SECURITY_MINIMUMS}))
    monkeypatch.setattr(sys,'path',list(sys.path));monkeypatch.setenv('PYTHONPATH','preserved')
    monkeypatch.setattr(importlib.metadata,'version',lambda name:SECURITY_MINIMUMS[name])
    assert activate_security_profile(tmp_path) and sys.path[0]==str(folder.resolve())
    assert os.environ['PYTHONPATH'].split(os.pathsep)==[str(folder.resolve()),'preserved']


def test_incomplete_or_mismatched_profile_preserves_import_and_spawn_paths(tmp_path,monkeypatch):
    import sys,os,importlib.metadata
    from geoforma.runtime_profile import activate_security_profile,SECURITY_MINIMUMS
    folder=tmp_path/'environment/security-runtime';folder.mkdir(parents=True)
    profile={'validated':True,'python':sys.implementation.cache_tag,'platform':sys.platform,'versions':{'torch':'2.13.0'}}
    marker=folder/'geoforma-profile.json';marker.write_text(json.dumps(profile))
    previous=list(sys.path);monkeypatch.setenv('PYTHONPATH','preserved')
    with pytest.raises(ValueError):activate_security_profile(tmp_path)
    profile['versions']=SECURITY_MINIMUMS;marker.write_text(json.dumps(profile))
    monkeypatch.setattr(importlib.metadata,'version',lambda name:'0')
    with pytest.raises(RuntimeError,match='版本不一致'):activate_security_profile(tmp_path)
    assert sys.path==previous and os.environ['PYTHONPATH']=='preserved'


def test_offline_release_model_matches_fresh_application_default_and_rejects_other_weights(tmp_path,monkeypatch):
    from tools.build_release import offline_checkpoint
    from geoforma.model_preferences import recommended_model
    from geoforma.model_catalog import model_spec
    config=recommended_model();expected=model_spec(config['variant'],config['backend'])
    weight=tmp_path/'renamed-checkpoint.pt';weight.write_bytes(b'isolated checkpoint')
    monkeypatch.setattr('geoforma.model_preferences.recommended_model',lambda:dict(config,checkpoint=str(weight)))
    monkeypatch.setattr('tools.build_release.sha',lambda path:expected['sha256'])
    spec,actual=offline_checkpoint();assert spec['id']=='sam2.1_small' and actual==weight
    assert spec['file']=='sam2.1_hiera_small.pt' and offline_checkpoint(weight)==(spec,weight)
    monkeypatch.setattr('tools.build_release.sha',lambda path:model_spec('vit_b')['sha256'])
    with pytest.raises(ValueError,match='默认模型'):offline_checkpoint(weight)
