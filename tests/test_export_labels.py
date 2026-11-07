"""Editable category values stay separate from references and reach exported files."""
import copy,json
from pathlib import Path
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
    dialog.add();dialog.name_inputs[2].setText('道路');assert dialog.commit_names();dialog.add();dialog.name_inputs[3].setText('建筑');assert dialog.commit_names()
    assert [class_value(c) for c in dialog.classes]==[1,2,3]
    dialog.value_inputs[2].setValue(20)
    assert [c['id'] for c in dialog.classes]==[1,2,3]
    dialog.add();dialog.name_inputs[4].setText('农田');assert dialog.commit_names();assert dialog.value_inputs[4].value()==21
    dialog.value_inputs[1].setValue(8);dialog.list.setCurrentCell(0,0);assert not dialog.delete_button.isEnabled()
    assert project['classes']==original
    project['classes'],project['next_class_id'],_=dialog.value();project['export_label_field']='landcover'
    snapshot=project_snapshot(project);project['classes'][0]['value']=9
    path=tmp_path/'labels.gfm';save_project(snapshot,path);loaded=load_project(path)
    assert loaded['classes']==snapshot['classes'] and loaded['classes'][0]['value']==8
    assert loaded['export_label_field']=='landcover'
    dialog.reject();dialog.deleteLater();app.processEvents()


def test_duplicate_value_edit_is_rejected_and_cancel_keeps_original():
    app=QApplication.instance() or QApplication([]);original=[dict(id=1,name='湖泊'),dict(id=2,name='道路')]
    dialog=ClassesDialog(original,3,{1},1)
    dialog.value_inputs[1].setValue(2)
    assert dialog.value_inputs[1].value()==1 and '唯一' in dialog.status.currentMessage()
    dialog.value_inputs[1].setValue(42);dialog.list.setCurrentCell(0,0)
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
    dialog.add();dialog.name_inputs[1].setText('湖泊');assert dialog.commit_names();assert class_value(dialog.classes[0])==1
    dialog.value_inputs[1].setValue(65534);dialog.add();dialog.name_inputs[2].setText('道路');assert dialog.commit_names()
    assert [c['id'] for c in dialog.classes]==[1,2] and class_value(dialog.classes[-1])==1
    dialog.close();dialog.deleteLater();app.processEvents()


def test_legacy_project_without_export_values_keeps_original_codes(tmp_path):
    project=new_project();project.pop('export_label_field');project['classes']=[dict(id=7,name='湖泊')]
    path=tmp_path/'legacy.gfm';path.write_text(json.dumps(project),encoding='utf-8')
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


def test_candidate_cannot_replace_existing_vector_export(source,tmp_path):
    labels=labels_for(source);labels.append(dict(labels[0],id='candidate',class_id=None,status='candidate',geometry=mapping(box(50,40,60,50))))
    path=tmp_path/'defaults.gpkg';path.write_bytes(b'existing')
    with pytest.raises(ValueError,match='只能导出已保存'):
        export_vector(source,labels,path,'',Task(),[dict(id=7,name='湖泊',value=42)])
    assert path.read_bytes()==b'existing'


def test_default_label_field_exports_shapefile_without_manual_rename(source,tmp_path):
    path=tmp_path/'default.shp';export_vector(source,labels_for(source),path,'',Task(),[dict(id=7,name='湖泊',value=42)])
    ds=ogr.Open(str(path));feature=ds.GetLayer(0).GetNextFeature()
    assert feature.GetField('class_val')==42
    ds=None
    assert json.loads(path.with_suffix('.metadata.json').read_text(encoding='utf-8'))['label_field']=='class_val'


@pytest.mark.parametrize('change,message',[
    ({'class_id':None},'有效类别'),({'class_id':True},'有效类别'),
    ({'image_id':'another-image'},'当前影像'),({'status':'draft'},'只能导出已保存'),
    ({'geometry':mapping(box(-1,5,10,20))},'超出当前影像范围')])
@pytest.mark.parametrize('kind',['vector','raster'])
def test_invalid_labels_do_not_replace_exports(source,tmp_path,change,message,kind):
    labels=labels_for(source);labels[0].update(change)
    path=tmp_path/('existing.gpkg' if kind=='vector' else 'existing.tif');path.write_bytes(b'existing')
    with pytest.raises(ValueError,match=message):
        if kind=='vector':export_vector(source,labels,path,'',Task())
        else:export_raster(source,labels,path,Task())
    assert path.read_bytes()==b'existing'


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
    w.export_kind.setCurrentIndex(w.export_kind.findData('.geojson'))
    monkeypatch.setattr('geoforma.controllers.exports.QFileDialog.getSaveFileName',lambda *args:(str(path),'GeoJSON (*.geojson)'))
    w.export();wait()
    feature=json.loads(path.read_text(encoding='utf-8'))['features'][0]
    assert feature['properties']['landcover']==42 and w.project['labels'][0]['class_id']==7 and not errors


@pytest.mark.parametrize('suffix,driver,filter_text',[
    ('.gpkg','GPKG','*.gpkg'),('.shp','ESRI Shapefile','*.shp'),('.geojson','GeoJSON','*.geojson'),
])
def test_format_selector_controls_dialog_and_actual_output(workbench,source,tmp_path,monkeypatch,suffix,driver,filter_text):
    from osgeo import ogr
    w,app,wait,errors=workbench;w.image=source;w.project['images']=[source]
    w.project['classes']=[dict(id=7,name='湖泊',value=42)]
    w.project['labels']=[dict(labels_for(source)[0],annotation_mode='individual')]
    w.export_kind.setCurrentIndex(w.export_kind.findData(suffix));dialog=[]
    def save_dialog(*args):
        dialog.append(args);return str(tmp_path/'selected.v2'),''
    monkeypatch.setattr('geoforma.controllers.exports.QFileDialog.getSaveFileName',save_dialog)
    w.export();wait()
    path=tmp_path/('selected.v2'+suffix);dataset=ogr.Open(str(path))
    assert dataset is not None and dataset.GetDriver().GetName()==driver
    assert w.statusBar().currentMessage()=='标签已导出 · '+path.name
    assert filter_text in dialog[0][3] and Path(dialog[0][2]).name==Path(source['path']).stem+'_labels' and not errors
    dataset=None


@pytest.mark.parametrize('name',['selected','selected.shp'])
def test_changed_extension_does_not_overwrite_without_confirmation(workbench,source,tmp_path,monkeypatch,name):
    from PySide6.QtWidgets import QMessageBox
    w,app,wait,errors=workbench;w.image=source;w.project['images']=[source]
    w.project['labels']=[dict(labels_for(source)[0],annotation_mode='individual')]
    target=tmp_path/'selected.gpkg';target.write_bytes(b'keep')
    monkeypatch.setattr('geoforma.controllers.exports.QFileDialog.getSaveFileName',lambda *args:(str(tmp_path/name),''))
    asked=[]
    monkeypatch.setattr(QMessageBox,'question',lambda *args:(asked.append(args) or QMessageBox.StandardButton.No))
    w.export();assert len(asked)==1 and target.read_bytes()==b'keep' and w.task is None and not errors


def test_shapefile_export_keeps_source_metadata_without_editing_sessions(workbench,source,tmp_path,monkeypatch):
    w,app,wait,errors=workbench;w.image=source;w.project['images']=[source]
    w.project['classes']=[dict(id=7,name='湖泊',value=42)]
    w.project['labels']=[dict(labels_for(source)[0],annotation_mode='individual')]
    source['mode_sessions']={'individual':{'draft':{'points':[[10,10,1]]}}}
    w.export_kind.setCurrentIndex(w.export_kind.findData('.shp'))
    path=tmp_path/'workflow.shp'
    monkeypatch.setattr('geoforma.controllers.exports.QFileDialog.getSaveFileName',lambda *args:(str(path),''))
    w.export();wait()
    metadata=json.loads(path.with_suffix('.metadata.json').read_text(encoding='utf-8'))
    assert metadata['source_image']['path']==source['path']
    assert metadata['source_image']['source_paths']==source['source_paths']
    assert 'mode_sessions' not in metadata['source_image'] and not errors
