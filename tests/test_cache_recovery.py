"""Recover ready images only when their existing feature blocks match."""
import hashlib
from zipfile import ZipFile, ZIP_STORED
import pytest
from geoforma.cache_recovery import descriptor, reconcile_prepared
from geoforma.domain import digest, new_project, tiles
from geoforma.workflow import full_bounds, fully_prepared
from test_workbench import fake_image, workbench
from test_project_loading import saved_project, wait_loading
from test_reshape import raster_image


def test_migrated_checkpoint_remaps_only_recorded_missing_managed_files(tmp_path, monkeypatch):
    import json
    from geoforma.cache_recovery import remap_migrated_checkpoint
    from geoforma.domain import data_dir
    root=data_dir();source=tmp_path/'old';middle=tmp_path/'middle';destination=tmp_path/'new'
    (destination/'models').mkdir(parents=True);target=destination/'models'/'weight.pt';target.write_bytes(b'weights')
    history={'kind':'geoforma-resource-migration-history-v1','migrations':[
        {'source':str(source),'destination':str(middle),'models':['models/weight.pt']},
        {'source':str(middle),'destination':str(destination),'models':['models/weight.pt']} ]}
    (root/'resource-migration-history.json').write_text(json.dumps(history),encoding='utf-8')
    project={'model':{'checkpoint':str(source/'models'/'weight.pt')}}
    assert remap_migrated_checkpoint(project)
    assert project['model']['checkpoint']==str(target)
    unrelated={'model':{'checkpoint':str(tmp_path/'external'/'weight.pt')}}
    assert not remap_migrated_checkpoint(unrelated)
    (source/'models').mkdir(parents=True);(source/'models'/'weight.pt').write_bytes(b'original')
    original={'model':{'checkpoint':str(source/'models'/'weight.pt')}}
    assert not remap_migrated_checkpoint(original)


def test_migration_does_not_remap_to_missing_or_unlisted_weights(tmp_path):
    import json
    from geoforma.cache_recovery import remap_migrated_checkpoint
    from geoforma.domain import data_dir
    source=tmp_path/'old';destination=tmp_path/'new'
    history={'kind':'geoforma-resource-migration-history-v1','migrations':[
        {'source':str(source),'destination':str(destination),'models':['models/weight.pt','models/../other.pt']} ]}
    (data_dir()/'resource-migration-history.json').write_text(json.dumps(history),encoding='utf-8')
    for name in ('weight.pt','other.pt'):
        model={'model':{'checkpoint':str(source/'models'/name)}}
        assert not remap_migrated_checkpoint(model)


def test_recovery_prefers_recorded_migration_even_if_old_file_remains(tmp_path):
    import json
    from geoforma.domain import data_dir
    from geoforma.recovery import recovery_target
    source=tmp_path/'old';destination=tmp_path/'new'
    for root in (source,destination):(root/'recovery').mkdir(parents=True)
    old=source/'recovery'/'untitled.gfm';old.write_text('{"images":[{}]}')
    new=destination/'recovery'/'untitled.gfm';new.write_text('{"images":[{}]}')
    history={'kind':'geoforma-resource-migration-history-v1','migrations':[
        {'source':str(source),'destination':str(destination),'recoveries':['recovery/untitled.gfm']} ]}
    (data_dir()/'resource-migration-history.json').write_text(json.dumps(history),encoding='utf-8')
    class Settings:
        def value(self,key,default=''):return str(old) if key=='recovery/last_work' else default
    assert recovery_target(Settings(),destination,data_dir())==new


def test_recovery_does_not_follow_obsolete_autosave(tmp_path):
    import json
    from geoforma.domain import data_dir
    from geoforma.cache_recovery import remap_migrated_path
    source=tmp_path/'old';destination=tmp_path/'new';(destination/'recovery').mkdir(parents=True)
    (destination/'recovery'/'untitled.gfm.autosave').write_text('saved')
    history={'kind':'geoforma-resource-migration-history-v1','migrations':[
        {'source':str(source),'destination':str(destination),'recoveries':['recovery/untitled.gfm.autosave']} ]}
    (data_dir()/'resource-migration-history.json').write_text(json.dumps(history),encoding='utf-8')
    old=source/'recovery'/'untitled.gfm'
    assert remap_migrated_path(old,'recoveries',preserve_existing=False) is None
    assert remap_migrated_path(tmp_path/'external'/'untitled.gfm','recoveries',preserve_existing=False) is None


def test_relocated_weight_preserves_prepared_feature_after_project_reload(tmp_path,monkeypatch):
    import json
    from geoforma.cache_recovery import remap_migrated_checkpoint
    from geoforma.domain import data_dir
    from geoforma import raster
    source=tmp_path/'old';destination=tmp_path/'new'
    (source/'models').mkdir(parents=True);(destination/'models').mkdir(parents=True)
    old=source/'models'/'weight.pt';old.write_bytes(b'model')
    project=new_project();model=project['model'];model['checkpoint']=str(old)
    image=fake_image('image');image.update(ready=True,prepared_cache_revision='revision',prepared_full_signature='old')
    project['images']=[image]
    monkeypatch.setattr(raster,'fingerprint',lambda path:image['fingerprint'])
    features=destination/'cache'/'features';features.mkdir(parents=True)
    sha=hashlib.sha256(b'model').hexdigest()
    for window in tiles(full_bounds(image),image['width'],image['height']):
        with ZipFile(features/(digest(descriptor(model,image,window,sha))+'.pt'),'w',compression=ZIP_STORED) as archive:archive.writestr('archive/data.pkl',b'fixture')
    (destination/'models'/'weight.pt').write_bytes(old.read_bytes());old.unlink()
    history={'kind':'geoforma-resource-migration-history-v1','migrations':[
        {'source':str(source),'destination':str(destination),'models':['models/weight.pt']} ]}
    (data_dir()/'resource-migration-history.json').write_text(json.dumps(history),encoding='utf-8')
    assert remap_migrated_checkpoint(project)
    assert reconcile_prepared(project,destination,'revision')==1
    assert fully_prepared(image,model)


def test_project_loading_remaps_recorded_moved_weight(tmp_path):
    import json
    from geoforma.domain import data_dir
    from geoforma.project_loading import prepare_project
    from geoforma.storage import save_project
    source=tmp_path/'old';destination=tmp_path/'new';(destination/'models').mkdir(parents=True)
    target=destination/'models'/'weight.pt';target.write_bytes(b'model')
    project=new_project();project['model']['checkpoint']=str(source/'models'/'weight.pt')
    project_path=tmp_path/'project.gfm';save_project(project,project_path)
    history={'kind':'geoforma-resource-migration-history-v1','migrations':[
        {'source':str(source),'destination':str(destination),'models':['models/weight.pt']} ]}
    (data_dir()/'resource-migration-history.json').write_text(json.dumps(history),encoding='utf-8')
    loaded=prepare_project(project_path,(800,600),read_frame=False)
    assert loaded.project['model']['checkpoint']==str(target)
    # Loading is read-only; the on-disk project is saved only by the user.
    assert json.loads(project_path.read_text(encoding='utf-8'))['model']['checkpoint']==str(source/'models'/'weight.pt')


@pytest.mark.parametrize('problem', [None, 'missing', 'corrupt', 'source', 'weights', 'revision'])
def test_reconcile_old_signature_with_existing_cache(tmp_path, monkeypatch, problem):
    from geoforma import raster
    project=new_project();model=project['model'];checkpoint=tmp_path/'weights.pt';checkpoint.write_bytes(b'model')
    model['checkpoint']=str(checkpoint)
    image=fake_image('image');image.update(ready=True,prepared_cache_revision='revision',prepared_full_signature='old')
    project['images']=[image]
    monkeypatch.setattr(raster,'fingerprint',lambda path:'changed' if problem=='source' else image['fingerprint'])
    folder=tmp_path/'cache'/'features';folder.mkdir(parents=True)
    weight_hash=hashlib.sha256(b'model').hexdigest()
    paths=[]
    for window in tiles(full_bounds(image),image['width'],image['height']):
        path=folder/(digest(descriptor(model,image,window,weight_hash))+'.pt')
        with ZipFile(path,'w',compression=ZIP_STORED) as archive:archive.writestr('archive/data.pkl',b'fixture')
        paths.append(path)
    if problem=='missing':paths[0].unlink()
    if problem=='corrupt':paths[0].write_bytes(b'broken')
    if problem=='weights':checkpoint.write_bytes(b'other model')
    count=reconcile_prepared(project,tmp_path,'other' if problem=='revision' else 'revision')
    assert count==(1 if problem is None else 0)
    assert fully_prepared(image,model)==(problem is None)


def test_unavailable_cache_is_not_reconciled_or_allowed_to_block_project_loading(tmp_path,monkeypatch):
    from geoforma import feature_cache
    project=new_project();checkpoint=tmp_path/'weights.pt';checkpoint.write_bytes(b'model')
    project['model']['checkpoint']=str(checkpoint)
    image=fake_image('image');image.update(ready=True,prepared_cache_revision='revision',prepared_full_signature='old')
    project['images']=[image]
    monkeypatch.setattr(feature_cache,'feature_directory',lambda root:(_ for _ in ()).throw(ValueError('linked')))
    assert reconcile_prepared(project,tmp_path,'revision')==0
    assert not fully_prepared(image,project['model'])


def test_recover_project_keeps_reconciled_image_ready(workbench, saved_project, tmp_path, monkeypatch):
    from geoforma.domain import data_dir
    from geoforma.storage import save_project
    w,app,wait,errors=workbench;path,project=saved_project;root=data_dir()
    checkpoint=tmp_path/'weights.pt';checkpoint.write_bytes(b'model')
    project['model']['checkpoint']=str(checkpoint);image=project['images'][0]
    w.service.activate_project(root,project['cache_id'])
    image.update(prepared_cache_revision=w.service.cache_revision,prepared_full_signature='old')
    folder=root/'cache'/'features';folder.mkdir(parents=True,exist_ok=True)
    weight_hash=hashlib.sha256(b'model').hexdigest()
    for window in tiles(full_bounds(image),image['width'],image['height']):
        cache=folder/(digest(descriptor(project['model'],image,window,weight_hash))+'.pt')
        with ZipFile(cache,'w',compression=ZIP_STORED) as archive:archive.writestr('archive/data.pkl',b'fixture')
    save_project(project,path)
    preprocessing=[];monkeypatch.setattr(w.service,'preprocess',lambda *args:preprocessing.append(args))
    monkeypatch.setattr(w.service,'prepare_model',lambda config,task:dict(checkpoint=config['checkpoint'],device='cpu',execution='native'))
    w.auto_prepare=True
    assert w.request_project_open(path,recover_latest=True)
    wait_loading(w,app);wait()
    assert w.image['ready'] and fully_prepared(w.image,w.project['model'])
    assert not preprocessing and not errors
