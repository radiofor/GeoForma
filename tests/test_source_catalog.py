import copy,json,shutil,time
from pathlib import Path
import pytest
from rasterio.shutil import copy as copy_raster
from geoforma.domain import new_project
from geoforma.storage import load_project,save_project,project_snapshot
from geoforma.source_catalog import SourceGuard,project_sources
from geoforma.exports import export_vector
from geoforma.raster import inspect_source
from test_reference_images import raster
from test_spatial_storage import Task


def project_with_sources(folder):
    project=new_project();project['images']=[raster(folder/'rgb'/'tile.tif')]
    reference=raster(folder/'ndwi'/'tile.tif');reference['group']='NDWI'
    manifest=folder/'references.yaml';manifest.write_text('format: geoforma-image-list',encoding='utf-8')
    reference['import_list']={'source':str(manifest)};project['references']=[reference]
    return project


def test_background_snapshots_detach_paths_without_copying_workbench_sessions(tmp_path):
    from geoforma.raster_snapshot import image_snapshot
    from geoforma.source_catalog import guard_snapshot
    class Uncopyable:
        def __deepcopy__(self,memo):raise AssertionError('Unrelated editing data was copied')
    image={'id':'one','path':str(tmp_path/'source.tif'),'source_paths':[str(tmp_path/'tile.tif')],
           'model_recipe':{'bands':[1,1,1]},'mode_sessions':{'draft':Uncopyable()}}
    reference={'path':str(tmp_path/'reference.tif'),'source_paths':[str(tmp_path/'reference.tif')],
               'import_list':{'source':str(tmp_path/'catalog.vrt'),'source_paths':[str(tmp_path/'nested.vrt')],
                              'note':Uncopyable()},'unused':Uncopyable()}
    project={'images':[image],'references':[reference]}
    detached=image_snapshot(image);protected=guard_snapshot(project)
    image['source_paths'].append(str(tmp_path/'later.tif'))
    image['model_recipe']['bands'][0]=2
    reference['import_list']['source_paths'].clear()
    assert detached['model_recipe']['bands']==[1,1,1] and len(detached['source_paths'])==1
    assert protected[0]['source_paths']==[str(tmp_path/'tile.tif')]
    assert protected[1]['import_list']['source_paths']==[str(tmp_path/'nested.vrt')]
    with pytest.raises(ValueError,match='覆盖源影像'):
        SourceGuard(protected).check(tmp_path/'nested.vrt')


def test_portable_reference_sources_and_provenance_roundtrip(tmp_path):
    original=tmp_path/'original';project=project_with_sources(original)
    path=original/'work.gfm';before=copy.deepcopy(project);save_project(project,path)
    assert project==before
    payload=json.loads(path.read_text(encoding='utf-8'))
    assert not Path(payload['references'][0]['path']).is_absolute()
    assert not Path(payload['references'][0]['source_paths'][0]).is_absolute()
    assert not Path(payload['references'][0]['import_list']['source']).is_absolute()
    moved=tmp_path/'moved';shutil.copytree(original,moved)
    loaded=load_project(moved/path.name)
    assert loaded['references'][0]['path']==str((moved/'ndwi'/'tile.tif').resolve())
    assert loaded['references'][0]['source_paths']==[str((moved/'ndwi'/'tile.tif').resolve())]
    assert loaded['references'][0]['import_list']['source']==str((moved/'references.yaml').resolve())


def test_autosave_detaches_reference_catalog_and_nested_metadata(tmp_path):
    project=project_with_sources(tmp_path);snapshot=project_snapshot(project)
    before=copy.deepcopy(snapshot['references'])
    project['references'][0]['display_recipe']['ranges'][0][0]=-100
    project['references'][0]['source_paths'].append('other.tif')
    project['references'][:]=[]
    assert snapshot['references']==before


@pytest.mark.parametrize('source_kind',['main','reference','manifest'])
def test_project_save_cannot_overwrite_any_imported_source(tmp_path,source_kind):
    project=project_with_sources(tmp_path)
    target=Path(project['images'][0]['path'] if source_kind=='main' else
                project['references'][0]['import_list']['source'] if source_kind=='manifest' else project['references'][0]['path'])
    protected=target
    original=protected.read_bytes()
    with pytest.raises(ValueError,match='覆盖'):save_project(project,target)
    assert protected.read_bytes()==original


def test_vrt_sources_discovered_for_legacy_records_and_only_once(tmp_path,monkeypatch):
    image=raster(tmp_path/'source.tif');vrt=tmp_path/'mosaic.vrt'
    copy_raster(image['path'],str(vrt),driver='VRT')
    descriptor=inspect_source(vrt);descriptor.pop('source_paths')
    import rasterio
    real_open=rasterio.open;calls=[]
    def counted(*args,**kwargs):calls.append(args[0]);return real_open(*args,**kwargs)
    monkeypatch.setattr(rasterio,'open',counted)
    guard=SourceGuard([descriptor,descriptor]);assert len(calls)==1
    with pytest.raises(ValueError,match='覆盖'):guard.check(image['path'])
    project=new_project();project['images']=[descriptor]
    before=Path(image['path']).read_bytes()
    with pytest.raises(ValueError,match='覆盖'):save_project(project,image['path'])
    assert Path(image['path']).read_bytes()==before


def test_shapefile_companion_cannot_replace_reference(tmp_path):
    project=project_with_sources(tmp_path);path=tmp_path/'labels.shp'
    ref=project['references'][0];companion=tmp_path/'labels.dbf';companion.write_bytes(b'protected reference')
    ref['source_paths'].append(str(companion))
    with pytest.raises(ValueError,match='覆盖'):
        export_vector(project['images'][0],[],path,'',Task(),sources=project_sources(project),label_field='class_val')
    assert companion.read_bytes()==b'protected reference'
    assert not path.exists() and not list(tmp_path.glob('.geoforma-vector-*'))


def test_missing_optional_reference_can_still_be_saved(tmp_path):
    project=project_with_sources(tmp_path);Path(project['references'][0]['path']).unlink()
    path=tmp_path/'work.gfm';save_project(project,path)
    assert load_project(path)['references'][0]['path']==project['references'][0]['path']


def test_inspection_opens_raster_once_and_retains_all_source_paths(tmp_path,monkeypatch):
    image=raster(tmp_path/'source.tif')
    import rasterio
    real_open=rasterio.open;calls=[]
    def counted(*args,**kwargs):calls.append(args[0]);return real_open(*args,**kwargs)
    monkeypatch.setattr(rasterio,'open',counted)
    result=inspect_source(image['path'])
    assert len(calls)==1 and result['fingerprint']==image['fingerprint']
    assert result['source_paths']==[image['path']]


def test_late_autosave_keeps_capture_order_after_newer_manual_save(tmp_path):
    project=new_project();project['name']='older state';snapshot=project_snapshot(project)
    time.sleep(.005);project['name']='newer manual save'
    path=tmp_path/'work.gfm';autosave=tmp_path/'snapshot.gfm'
    save_project(project,path);save_project(snapshot,autosave)
    assert autosave.stat().st_mtime_ns<path.stat().st_mtime_ns
    assert load_project(path)['name']=='newer manual save'
    assert '_snapshot_time_ns' not in json.loads(autosave.read_text(encoding='utf-8'))
    assert load_project(autosave)['name']=='older state'


def test_expanded_vrt_provenance_chain_is_portable_and_protected(tmp_path):
    original=tmp_path/'original';project=project_with_sources(original)
    root=original/'batch.vrt';nested=original/'nested.vrt'
    for path in (root,nested):path.write_text('<VRTDataset/>',encoding='utf-8')
    project['images'][0]['import_list']={'source':str(root),'source_paths':[str(root),str(nested)]}
    guard=SourceGuard(project_sources(project))
    for path in (root,nested):
        with pytest.raises(ValueError,match='覆盖'):guard.check(path)
    project_file=original/'work.gfm';save_project(project,project_file)
    payload=json.loads(project_file.read_text(encoding='utf-8'))
    assert all(not Path(value).is_absolute() for value in payload['images'][0]['import_list']['source_paths'])
    moved=tmp_path/'moved';shutil.copytree(original,moved);loaded=load_project(moved/project_file.name)
    assert loaded['images'][0]['import_list']['source_paths']==[str(moved/'batch.vrt'),str(moved/'nested.vrt')]
