"""Disconnected results become separate rows with one atomic undo history."""
import copy
import pytest
from shapely.geometry import box,mapping,shape,MultiPolygon
from geoforma.label_parts import split_label
from test_reshape import workbench,raster_image


def disconnected():
    return mapping(MultiPolygon([box(10,10,20,20).difference(box(12,12,14,14)),box(40,40,45,45)]))


def test_split_preserves_holes_identity_and_independent_metadata():
    label={'id':'source','geometry':disconnected(),'class_id':3,'points':[[15,15,1]],'raw_geometry':disconnected()}
    before=copy.deepcopy(label);parts=split_label(label)
    assert parts[0]['id']=='source' and parts[1]['id']!='source'
    assert all(p['geometry']['type']=='Polygon' and p['class_id']==3 and 'raw_geometry' not in p for p in parts)
    assert len(shape(parts[0]['geometry']).interiors)==1 and label==before
    parts[1]['points'].append([1,1,0]);assert parts[0]['points']==label['points']


@pytest.mark.parametrize('single',[False,True])
def test_save_components_as_independent_rows_and_restore_history(workbench,single):
    w,app,tmp=workbench;w.project['labels']=[];w.single_polygon.setChecked(single)
    w.draft={'geometry':disconnected(),'points':[],'pending':False};w.refresh_labels();w.confirm()
    count=1 if single else 2
    assert len(w.project['labels'])==count and w.labels_table.rowCount()==count
    assert all(l['geometry']['type']=='Polygon' for l in w.project['labels'])
    assert len({l['id'] for l in w.project['labels']})==count and len(w.label_undo)==1
    assert all(row.status=='已保存' for row in w.label_presenter.rows)
    w.project_path=tmp/'parts.gfm';w.save();w.open_project(w.project_path)
    saved=copy.deepcopy(w.project['labels']);w.undo_label();assert not w.project['labels']
    w.redo_label();assert w.project['labels']==saved and w.labels_table.rowCount()==count


def test_overlap_cut_creates_independent_labels(workbench):
    w,app,_=workbench;w.single_polygon.setChecked(False)
    blocker=dict(w.project['labels'][0],geometry=mapping(box(24,10,26,40)))
    w.project['labels']=[blocker];w.draft={'geometry':mapping(box(20,20,30,30)),'points':[],'pending':False};w.confirm()
    assert len(w.project['labels'])==3 and w.labels_table.rowCount()==3
    assert all(l['geometry']['type']=='Polygon' for l in w.project['labels'])
    assert sorted(shape(l['geometry']).area for l in w.project['labels'] if l['id']!=blocker['id'])==[40,40]
    w.undo_label();assert w.project['labels']==[blocker]


def test_edit_existing_multicomponent_result_keeps_primary_id(workbench):
    w,app,_=workbench;w.single_polygon.setChecked(False);before=copy.deepcopy(w.project['labels'])
    w.draft={'base_id':'target','geometry':disconnected(),'points':[],'pending':False,'editing_state':'manual'};w.confirm()
    assert len(w.project['labels'])==2 and 'target' in {l['id'] for l in w.project['labels']}
    w.undo_label();assert w.project['labels']==before
    w.redo_label();assert len(w.project['labels'])==2
    w.select_label(next(l['id'] for l in w.project['labels'] if l['id']!='target'));w.delete_selected()
    assert len(w.project['labels'])==1 and w.project['labels'][0]['id']=='target'


def test_batch_save_splits_all_targets_and_undoes_as_one(workbench):
    w,app,_=workbench;w.single_polygon.setChecked(False)
    first=w.project['labels'][0];second=dict(first,id='second',geometry=mapping(box(70,70,80,80)))
    w.project['labels'].append(second);before=copy.deepcopy(w.project['labels'])
    a={'base_id':first['id'],'class_id':1,'geometry':disconnected(),'editing_state':'manual'}
    b={'base_id':second['id'],'class_id':1,'geometry':mapping(MultiPolygon([box(70,70,75,75),box(80,80,85,85)])),'editing_state':'manual'}
    w.draft=dict(a,reshape_batch=[a,b]);w.refresh_labels();w.confirm()
    assert len(w.project['labels'])==4 and w.labels_table.rowCount()==4
    assert all(l['geometry']['type']=='Polygon' for l in w.project['labels'])
    assert len(w.label_undo)==1
    saved=copy.deepcopy(w.project['labels']);w.undo_label();assert w.project['labels']==before
    w.redo_label();assert w.project['labels']==saved


@pytest.mark.parametrize('extension',['gpkg','shp','geojson'])
def test_export_keeps_independent_polygon_features(workbench,extension):
    from types import SimpleNamespace
    from osgeo import ogr
    from geoforma.vector_export import write_vector
    w,app,tmp=workbench;w.project['labels']=[];w.single_polygon.setChecked(False)
    w.draft={'geometry':disconnected(),'points':[],'pending':False};w.confirm()
    task=SimpleNamespace(check=lambda:None,signals=SimpleNamespace(progress=SimpleNamespace(emit=lambda *args:None)))
    path=tmp/f'parts.{extension}'
    write_vector(w.image,w.project['labels'],path,'',task,w.project['classes'],lambda *args:None,label_field='class_val')
    store=ogr.Open(str(path));layer=store.GetLayer()
    assert layer.GetFeatureCount()==2
    assert all(feature.GetGeometryRef().GetGeometryName()=='POLYGON' for feature in layer)
    store=None
