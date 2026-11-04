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


def test_format_selection_shows_actual_geojson_crs_without_changing_project():
    from PySide6.QtWidgets import QApplication
    from geoforma.window import MainWindow
    app=QApplication.instance() or QApplication([]);w=MainWindow(auto_prepare=False);w.autosave=lambda:None
    w.project['export_crs']='EPSG:3857';w.refresh_export_crs(force=True)
    w.export_kind.setCurrentIndex(w.export_kind.findData('.geojson'))
    assert w.export_crs_input.text()=='EPSG:4326' and w.export_crs_input.isReadOnly() and not w.export_crs_input.isEnabled()
    w.update_controls();assert not w.export_crs_input.isEnabled()
    w.commit_export_crs();assert w.project['export_crs']=='EPSG:3857'
    w.export_kind.setCurrentIndex(w.export_kind.findData('.shp'))
    assert w.export_crs_input.text()=='EPSG:3857' and not w.export_crs_input.isReadOnly() and w.export_crs_input.isEnabled()
    assert w.export_group.height()>=w.export_group.layout().minimumSize().height()
    w.dirty=False;w.close();app.processEvents()


@pytest.mark.parametrize('name,suffix,expected',[
    ('labels','.shp','labels.shp'),('labels.gpkg','.shp','labels.shp'),
    ('labels.v2','.geojson','labels.v2.geojson'),('labels.SHP','.shp','labels.SHP'),
])
def test_selected_format_controls_extension(tmp_path,name,suffix,expected):
    from geoforma.export_settings import export_path
    assert export_path(tmp_path/name,suffix)==str(tmp_path/expected)


