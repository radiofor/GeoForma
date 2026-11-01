from pathlib import Path
import pytest
from PySide6.QtCore import Qt,QMimeData,QPoint,QPointF,QUrl
from PySide6.QtGui import QDragEnterEvent,QDropEvent
from geoforma.storage import load_project,save_project
from test_workbench import workbench
from test_reshape import raster_image


def test_real_vrt_imports_individual_tiffs_with_independent_grids_and_provenance(workbench,raster_image,tmp_path):
    from osgeo import gdal
    from xml.etree import ElementTree as ET
    from copy import deepcopy
    gdal.UseExceptions();w,app,wait,errors=workbench
    source=Path(raster_image['path']);second=tmp_path/'second.tif'
    dataset=gdal.Translate(str(second),str(source));assert dataset is not None;dataset=None
    vrt=tmp_path/'batch.vrt';dataset=gdal.Translate(str(vrt),str(source),format='VRT');assert dataset is not None;dataset=None
    tree=ET.parse(vrt)
    for band in tree.getroot().findall('VRTRasterBand'):
        original=band.find('SimpleSource')
        if original is None:original=band.find('ComplexSource')
        extra=deepcopy(original);extra.find('SourceFilename').text=second.name;extra.find('SourceFilename').set('relativeToVRT','1');band.append(extra)
    tree.write(vrt,encoding='utf-8',xml_declaration=True)
    dataset=gdal.Open(str(vrt));assert dataset is not None;dataset=None
    broken=tmp_path/'broken.tif';broken.write_text('not a raster',encoding='utf-8')
    from geoforma.workflow import preparation_window
    reports=[];queued=[];w.show_import_report=lambda summary,details:reports.append((summary,details));w.queue_preparation=lambda:queued.extend(preparation_window(w.project['images'],w.image))
    w.import_paths([str(vrt),str(source),str(broken),str(tmp_path/'missing.tif')]);wait()
    assert len(w.project['images'])==2 and len(queued)==2 and not errors
    assert [Path(image['path']).name for image in w.project['images']]==[source.name,second.name]
    assert all(image['width']==raster_image['width'] and image['height']==raster_image['height'] for image in w.project['images'])
    assert all(image['transform']==raster_image['transform'] for image in w.project['images'])
    assert all(image['import_list']['source']==str(vrt) for image in w.project['images'])
    assert len(reports)==1 and len(reports[0][1])==2 and '重复 1 项' in reports[0][0]
    save_project(w.project,w.project_path);loaded=load_project(w.project_path)
    assert loaded['images'][0]['import_list']==w.project['images'][0]['import_list']
    with pytest.raises(ValueError,match='覆盖'):save_project(w.project,vrt)
    w.import_paths([str(vrt)]);wait();assert len(w.project['images'])==2 and len(queued)==2


def test_vrt_and_tiff_drop_are_accepted_but_yaml_list_is_rejected(workbench,tmp_path):
    w,app,wait,errors=workbench;imports=[];w.import_paths=lambda files:imports.extend(files)
    for suffix,accepted in (('.vrt',True),('.tif',True),('.tiff',True),('.yaml',False),('.yml',False),('.json',False)):
        mime=QMimeData();path=str(tmp_path/('source'+suffix));mime.setUrls([QUrl.fromLocalFile(path)])
        enter=QDragEnterEvent(QPoint(20,20),Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
        w.dragEnterEvent(enter);assert enter.isAccepted()==accepted
        drop=QDropEvent(QPointF(20,20),Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
        w.dropEvent(drop);assert any(Path(item)==Path(path) for item in imports)==accepted
