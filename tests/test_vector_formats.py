"""Geometry, UTF-8 attributes and old-output preservation across vector drivers."""
import copy,json
from pathlib import Path
import pytest
from osgeo import ogr
from shapely.geometry import Polygon,MultiPolygon,box,mapping,shape
from shapely.affinity import affine_transform
from rasterio.warp import transform_geom
from test_spatial_storage import source,Task
from geoforma.exports import export_vector


def labels_for(image):
    geometry=MultiPolygon([Polygon([(4,5),(30,5),(30,31),(4,31)],holes=[[(12,12),(16,12),(16,16),(12,16)]]),box(40,10,40.5,10.5)])
    return [{'id':'test-label','image_id':image['id'],'class_id':7,'status':'confirmed','geometry':mapping(geometry),'source':'interactive',
             'points':[[8.5,9.5,1],[14.5,14.5,0]],'box':[4,5,41,32],'model':{'backend':'sam2.1','variant':'small','provenance':'x'*500}}]


@pytest.mark.parametrize('ext',['gpkg','shp'])
def test_first_raster_crs_reprojects_labels_from_another_raster(source,tmp_path,ext):
    from geoforma.domain import new_project
    from geoforma.export_settings import target_crs
    project=new_project();project['images']=[{'crs':'EPSG:3857'},source]
    labels=labels_for(source);path=tmp_path/('first_raster_crs.'+ext)
    export_vector(source,labels,path,target_crs(project,source),Task(),label_field='class_val')
    ds=ogr.Open(str(path));layer=ds.GetLayer(0)
    assert layer.GetSpatialRef().GetAuthorityCode(None)=='3857'
    feature=layer.GetNextFeature();actual=shape(json.loads(feature.GetGeometryRef().ExportToJson()))
    a,b,c,d,e,f=source['transform']
    world=affine_transform(shape(labels[0]['geometry']),[a,b,d,e,c,f])
    expected=shape(transform_geom(source['crs'],'EPSG:3857',mapping(world)))
    assert actual.hausdorff_distance(expected)<1e-6
    ds=None


@pytest.mark.parametrize('ext',['gpkg','shp','geojson'])
def test_export_roundtrip_preserves_holes_small_parts_and_unicode(source,tmp_path,ext):
    labels=labels_for(source);classes=[{'id':7,'name':'冰碛湖'}];path=tmp_path/('labels.'+ext)
    export_vector(source,labels,path,'EPSG:32645',Task(),classes,label_field='class_val')
    ds=ogr.Open(str(path));layer=ds.GetLayer(0);assert layer.GetFeatureCount()==1
    feature=layer.GetNextFeature();assert feature.GetField('label_id')==labels[0]['id'] and feature.GetField('class_name')=='冰碛湖'
    g=json.loads(feature.GetGeometryRef().ExportToJson())
    if ext=='geojson':
        payload=json.loads(path.read_text(encoding='utf-8'));assert 'crs' not in payload
        assert layer.GetSpatialRef().GetAuthorityCode(None)=='4326'
        g=transform_geom('EPSG:4326',source['crs'],g)
    inverse=~__import__('rasterio').transform.Affine(*source['transform']);a,b,c,d,e,f=list(inverse)[:6]
    pixels=affine_transform(shape(g),[a,b,d,e,c,f]);assert pixels.hausdorff_distance(shape(labels[0]['geometry']))<1e-5
    assert pixels.symmetric_difference(shape(labels[0]['geometry'])).area<1e-5
    ds=None
    if ext=='shp':
        for suffix in ['.shp','.shx','.dbf','.prj','.cpg','.metadata.json']:assert path.with_suffix(suffix).exists()
        metadata=json.loads(path.with_suffix('.metadata.json').read_text(encoding='utf-8'));assert metadata['labels']==json.loads(json.dumps(labels)) and metadata['classes']==classes


@pytest.mark.parametrize('ext',['gpkg','shp','geojson'])
def test_cancel_preserves_previous_vector_set(source,tmp_path,ext):
    from geoforma.tasks import Cancelled
    path=tmp_path/('labels.'+ext);labels=labels_for(source);export_vector(source,labels,path,'',Task(),label_field='class_val')
    before={p.name:p.read_bytes() for p in tmp_path.glob('labels.*')}
    class Cancel(Task):
        def check(self):raise Cancelled()
    with pytest.raises(Cancelled):export_vector(source,labels,path,'',Cancel(),label_field='class_val')
    assert before=={p.name:p.read_bytes() for p in tmp_path.glob('labels.*')}
    assert not list(tmp_path.glob('.geoforma-vector-*'))


def test_export_cannot_overwrite_project_or_shapefile_sidecar(source,tmp_path):
    project=tmp_path/'labels.metadata.json';project.write_bytes(b'project')
    path=tmp_path/'labels.shp'
    with pytest.raises(ValueError,match='项目文件'):
        export_vector(source,labels_for(source),path,'',Task(),protected_paths=[project],label_field='class_val')
    assert project.read_bytes()==b'project' and not path.exists()


def test_shp_publish_failure_restores_all_original_files(source,tmp_path,monkeypatch):
    import geoforma.vector_export as writer
    path=tmp_path/'labels.shp';labels=labels_for(source);export_vector(source,labels,path,'',Task(),label_field='class_val')
    before={p.name:p.read_bytes() for p in tmp_path.glob('labels.*')};real_replace=writer.replace_file;failed=False
    def fail_once(src,dst):
        nonlocal failed
        if not failed and Path(src).suffix=='.shx' and Path(src).parent.name.startswith('.geoforma-vector-') and Path(dst).parent==tmp_path:
            failed=True;raise OSError('Simulated sharing violation')
        return real_replace(src,dst)
    monkeypatch.setattr(writer,'replace_file',fail_once)
    with pytest.raises(OSError):export_vector(source,labels,path,'EPSG:4326',Task(),label_field='class_val')
    assert failed and before=={p.name:p.read_bytes() for p in tmp_path.glob('labels.*')}


def test_shp_export_cannot_replace_an_image_dependency_sidecar(source,tmp_path):
    dependency=tmp_path/'labels.metadata.json';dependency.write_text('source dependency',encoding='utf-8')
    image=dict(source,source_paths=[*source.get('source_paths',[]),str(dependency)])
    with pytest.raises(ValueError,match='不能覆盖源影像'):
        export_vector(image,labels_for(image),tmp_path/'labels.shp','',Task(),label_field='class_val')
    assert dependency.read_text(encoding='utf-8')=='source dependency'
    assert not (tmp_path/'labels.shp').exists()


def test_new_shapefile_does_not_overwrite_unrelated_existing_sidecar(source,tmp_path):
    existing=tmp_path/'labels.dbf';existing.write_bytes(b'unrelated data')
    with pytest.raises(ValueError,match='同名 SHP 附属文件已存在'):
        export_vector(source,labels_for(source),tmp_path/'labels.shp','',Task(),label_field='class_val')
    assert existing.read_bytes()==b'unrelated data' and not (tmp_path/'labels.shp').exists()


def test_shp_full_class_name_is_retained_without_dbf_loss(source,tmp_path):
    name='冰碛湖'*120;path=tmp_path/'long.shp'
    export_vector(source,labels_for(source),path,'',Task(),[{'id':7,'name':name}],label_field='class_val')
    assert json.loads(path.with_suffix('.metadata.json').read_text(encoding='utf-8'))['classes'][0]['name']==name


@pytest.mark.parametrize('ext',['gpkg','shp','geojson'])
def test_overlapping_legacy_labels_cannot_overwrite_previous_exports(source,tmp_path,ext):
    path=tmp_path/('labels.'+ext);labels=labels_for(source)
    export_vector(source,labels,path,'',Task(),label_field='class_val')
    before={p.name:p.read_bytes() for p in tmp_path.glob('labels.*')}
    labels.append(dict(labels[0],id='overlapping',class_id=8))
    with pytest.raises(ValueError,match='存在重叠'):export_vector(source,labels,path,'',Task(),label_field='class_val')
    assert before=={p.name:p.read_bytes() for p in tmp_path.glob('labels.*')}
