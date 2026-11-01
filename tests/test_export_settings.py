import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from geoforma.domain import new_project
from geoforma.export_settings import target_crs


def test_projection_defaults_to_first_raster_and_ignores_current_raster():
    project=new_project();a={'crs':'EPSG:32644'};b={'crs':'EPSG:32645'}
    assert target_crs(project,{'id':'detached'})==''
    project['images']=[a,b]
    assert target_crs(project,a)==target_crs(project,b)=='EPSG:32644'
    b['assigned_crs']='EPSG:3857';assert target_crs(project,b)=='EPSG:32644'
    a['assigned_crs']='EPSG:3857';assert target_crs(project,b)=='EPSG:3857'
    project['export_crs']='EPSG:4326'
    assert target_crs(project,a)==target_crs(project,b)=='EPSG:4326'
    project['export_crs']='';assert target_crs(project,b)=='EPSG:3857'
    a.update(crs='',assigned_crs='')
    with pytest.raises(ValueError,match='第一个栅格'):target_crs(project,b)


def test_projection_edit_validation_and_default_controls():
    from PySide6.QtWidgets import QApplication,QLabel
    from geoforma.window import MainWindow
    app=QApplication.instance() or QApplication([]);w=MainWindow(auto_prepare=False);w.autosave=lambda:None
    w.image={'id':'a','crs':'EPSG:32644','width':1000,'height':1000,'model_recipe':None}
    w.project['images']=[w.image]
    w.update_controls();assert w.export_crs_input.text()=='EPSG:32644' and not w.export_crs_input.isReadOnly()
    assert not hasattr(w,'export_crs_fixed')
    assert [label.text() for label in w.image_info.findChildren(QLabel) if label.property('role')=='muted']==['尺寸','坐标系代码','坐标系名称','模型波段','文件目录']
    w.commit_export_crs();assert w.project['export_crs']==''
    w.export_crs_input.setText('EPSG:3857');w.commit_export_crs()
    w.image=dict(w.image,crs='EPSG:32645');w.update_controls();assert w.export_crs_input.text()=='EPSG:3857'
    w.export_crs_input.setText('bad-crs');w.commit_export_crs();assert w.project['export_crs']=='EPSG:3857'
    w.export_crs_input.clear();w.commit_export_crs();assert w.export_crs_input.text()=='EPSG:32644'
    w.project['images'][0]['assigned_crs']='EPSG:32646';w.update_controls();assert w.export_crs_input.text()=='EPSG:32646'
    w.image=None;w.project['images']=[];w.update_controls();assert not w.export_crs_input.text()
    w.dirty=False;w.close();app.processEvents()


@pytest.mark.parametrize('flag,expected',[(False,''),(True,'EPSG:3857'),(None,'EPSG:3857')])
def test_legacy_projection_migration_and_save(tmp_path,flag,expected):
    import json
    from geoforma.storage import save_project,load_project
    project=new_project();project['export_crs']='EPSG:3857'
    if flag is not None:project['export_crs_fixed']=flag
    path=tmp_path/'projection.geoforma.json';save_project(project,path);loaded=load_project(path)
    assert loaded['export_crs']==expected and 'export_crs_fixed' not in loaded
    save_project(loaded,path);assert 'export_crs_fixed' not in json.loads(path.read_text(encoding='utf-8'))
