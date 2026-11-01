"""Editable category values stay separate from references and reach exported files."""
import copy,json
import numpy as np
import pytest
import rasterio
from osgeo import ogr
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from shapely.geometry import box,mapping
from geoforma.classes import class_value,validate_classes
from geoforma.dialogs import ClassesDialog
from geoforma.domain import new_project
from geoforma.export_settings import label_field,validate_label_field
from geoforma.exports import export_vector,export_raster
from geoforma.storage import load_project,save_project,project_snapshot
from test_spatial_storage import source,Task
from test_vector_formats import labels_for
from test_workbench import workbench


def test_category_defaults_increment_and_custom_values_do_not_change_references(tmp_path):
    app=QApplication.instance() or QApplication([]);project=new_project();original=copy.deepcopy(project['classes'])
    dialog=ClassesDialog(project['classes'],2,{1},1)
    assert dialog.value_inputs[1].value()==1
    dialog.name.setText('道路');dialog.add();dialog.name.setText('建筑');dialog.add()
    assert [class_value(c) for c in dialog.classes]==[1,2,3]
    dialog.value_inputs[2].setValue(20)
    assert [c['id'] for c in dialog.classes]==[1,2,3]
    dialog.name.setText('农田');dialog.add();assert dialog.value_inputs[4].value()==21
    dialog.value_inputs[1].setValue(8);dialog.list.setCurrentRow(0);assert not dialog.delete_button.isEnabled()
    assert project['classes']==original
    project['classes'],project['next_class_id'],_=dialog.value();project['export_label_field']='landcover'
    snapshot=project_snapshot(project);project['classes'][0]['value']=9
    path=tmp_path/'labels.geoforma.json';save_project(snapshot,path);loaded=load_project(path)
    assert loaded['classes']==snapshot['classes'] and loaded['classes'][0]['value']==8
    assert loaded['export_label_field']=='landcover'
    dialog.reject();dialog.deleteLater();app.processEvents()


def test_duplicate_value_edit_is_rejected_and_cancel_keeps_original():
    app=QApplication.instance() or QApplication([]);original=[dict(id=1,name='湖泊'),dict(id=2,name='道路')]
    dialog=ClassesDialog(original,3,{1},1)
    dialog.value_inputs[1].setValue(2)
    assert dialog.value_inputs[1].value()==1 and '唯一' in dialog.message.text()
    dialog.value_inputs[1].setValue(42);dialog.list.setCurrentRow(0)
    assert not dialog.delete_button.isEnabled() and dialog.classes[0]['id']==1
    dialog.reject();assert original==[dict(id=1,name='湖泊'),dict(id=2,name='道路')]
    dialog.deleteLater();app.processEvents()


@pytest.mark.parametrize('value',[0,65535,-1,1.5,'1',True,None])
def test_invalid_category_values_are_rejected(value):
    with pytest.raises(ValueError,match='标签值'):validate_classes([dict(id=1,name='湖泊',value=value)])


def test_explicit_value_cannot_duplicate_a_legacy_default():
    with pytest.raises(ValueError,match='标签值'):validate_classes([dict(id=1,name='湖泊',value=2),dict(id=2,name='道路')])


def test_new_category_still_works_after_user_selects_the_highest_value():
    app=QApplication.instance() or QApplication([]);dialog=ClassesDialog([],1,set())
    dialog.name.setText('湖泊');dialog.add();assert class_value(dialog.classes[0])==1
    dialog.value_inputs[1].setValue(65534);dialog.name.setText('道路');dialog.add()
    assert [c['id'] for c in dialog.classes]==[1,2] and class_value(dialog.classes[-1])==1
    dialog.close();dialog.deleteLater();app.processEvents()


def test_legacy_project_without_export_values_keeps_original_codes(tmp_path):
    project=new_project();project.pop('export_label_field');project['classes']=[dict(id=7,name='湖泊')]
    path=tmp_path/'legacy.geoforma.json';path.write_text(json.dumps(project),encoding='utf-8')
    loaded=load_project(path)
    assert class_value(loaded['classes'][0])==7 and label_field(loaded)=='class_value'


@pytest.mark.parametrize('ext',['gpkg','shp','geojson'])
@pytest.mark.parametrize('field',['landcover','类别'])
def test_vector_files_store_custom_field_and_value(source,tmp_path,ext,field):
    labels=labels_for(source);before=copy.deepcopy(labels);classes=[dict(id=7,name='冰碛湖',value=42)]
    path=tmp_path/('custom.'+ext);export_vector(source,labels,path,'',Task(),classes,label_field=field)
    ds=ogr.Open(str(path));layer=ds.GetLayer(0);feature=layer.GetNextFeature()
    assert feature.GetField(field)==42 and feature.GetField('class_name')=='冰碛湖'
    assert feature.GetFieldIndex('class_id')==-1 and labels==before
    ds=None
    if ext=='shp':
        metadata=json.loads(path.with_suffix('.metadata.json').read_text(encoding='utf-8'))
        assert metadata['label_field']==field and metadata['classes']==classes and metadata['labels'][0]['class_id']==7


def test_default_field_uses_custom_value_and_unclassified_candidates_stay_null(source,tmp_path):
    labels=labels_for(source);labels.append(dict(labels[0],id='candidate',class_id=None,status='candidate',geometry=mapping(box(50,40,60,50))))
    path=tmp_path/'defaults.gpkg';export_vector(source,labels,path,'',Task(),[dict(id=7,name='湖泊',value=42)])
    ds=ogr.Open(str(path));layer=ds.GetLayer(0)
    assert layer.GetNextFeature().GetField('class_value')==42
    assert layer.GetNextFeature().GetField('class_value') is None
    ds=None


def test_raster_uses_custom_values_and_keeps_unlabeled_nodata_and_grid(source,tmp_path):
    labels=labels_for(source);path=tmp_path/'values.tif'
    export_raster(source,labels,path,Task(),[dict(id=7,name='湖泊',value=42)])
    with rasterio.open(path) as ds:
        assert set(np.unique(ds.read(1)))=={0,42,65535}
        assert ds.read(1)[6,6]==42 and ds.transform==rasterio.Affine(*source['transform'])
        assert json.loads(ds.tags()['classes'])[0]['value']==42


@pytest.mark.parametrize('field',['',' ','label_id','CLASS_NAME','FID','geom','rowid','has space','bad-name','2label','x'*64])
def test_invalid_field_is_rejected(field):
    with pytest.raises(ValueError):validate_label_field(field)


def test_long_shp_field_does_not_modify_existing_output(source,tmp_path):
    path=tmp_path/'existing.shp';export_vector(source,labels_for(source),path,'',Task(),label_field='class_val')
    before={p.name:p.read_bytes() for p in tmp_path.glob('existing.*')}
    with pytest.raises(ValueError,match='10 个'):export_vector(source,labels_for(source),path,'',Task(),label_field='long_field_name')
    assert before=={p.name:p.read_bytes() for p in tmp_path.glob('existing.*')}
    assert not list(tmp_path.glob('.geoforma-vector-*'))


def test_export_field_edit_persists_and_control_refresh_preserves_typing(workbench):
    w,app,wait,errors=workbench;control=w.export_label_field_input
    assert control.text()=='class_value'
    control.setText('landcover');assert w.commit_export_label_field()
    assert w.project['export_label_field']=='landcover' and w.dirty
    control.setFocus();control.selectAll();QTest.keyClicks(control,'labels');w.update_controls()
    assert control.text()=='labels'
    assert w.commit_export_label_field() and w.project['export_label_field']=='labels'
    control.setText('class_name');assert not w.commit_export_label_field()
    assert control.text()=='labels' and w.project['export_label_field']=='labels'
    w.project=new_project();w.refresh_export_label_field(force=True);assert control.text()=='class_value'
    w.task=object()
    try:w.update_controls();assert not control.isEnabled()
    finally:w.task=None;w.update_controls()
    assert not errors


def test_export_workflow_passes_field_and_values_to_writer(workbench,source,tmp_path,monkeypatch):
    w,app,wait,errors=workbench;w.image=source;w.project['images']=[source]
    w.project['classes']=[dict(id=7,name='湖泊',value=42)]
    w.project['labels']=[dict(labels_for(source)[0],annotation_mode='individual')]
    path=tmp_path/'workflow.geojson';w.export_label_field_input.setText('landcover')
    monkeypatch.setattr('geoforma.controllers.exports.QFileDialog.getSaveFileName',lambda *args:(str(path),'GeoJSON (*.geojson)'))
    w.export('gpkg');wait()
    feature=json.loads(path.read_text(encoding='utf-8'))['features'][0]
    assert feature['properties']['landcover']==42 and w.project['labels'][0]['class_id']==7 and not errors
