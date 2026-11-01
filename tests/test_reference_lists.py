from pathlib import Path
from test_image_list import write_vrt
from geoforma.storage import save_project,load_project
from test_workbench import workbench
from test_reference_images import raster


def test_vrt_references_expand_tiffs_skip_unmatched_and_keep_provenance(workbench,tmp_path,monkeypatch):
    from geoforma.controllers import references as flow
    w,app,wait,errors=workbench
    base=raster(tmp_path/'rgb'/'tile.tif');reference=raster(tmp_path/'NDWI'/'tile.tif')
    w.project['images']=[base];w.refresh_images();w.images.setCurrentRow(0)
    path=write_vrt(tmp_path,['NDWI/tile.tif','not_existing_other.tif'],name='refs.vrt',bands=3)
    calls=[];read=flow.inspect_source
    monkeypatch.setattr(flow,'inspect_source',lambda value:(calls.append(value),read(value))[1])
    reports=[];w.show_import_report=lambda *args:reports.append(args)
    w.import_reference_paths([str(path),reference['path']],'NDWI');wait()
    assert calls==[reference['path']] and len(w.project['references'])==1
    assert w.project['references'][0]['import_list']['source']==str(path)
    assert w.project['references'][0]['reference_origin']=={'kind':'vrt','name':path.name}
    assert w.statusBar().currentMessage()=='NDWI · 成功 1 幅 · 跳过 2 项'
    record=w.log.toPlainText()
    assert '未匹配跳过 1 幅' in record and '重复 1 项' in record
    assert not reports and not errors and len(w.project['images'])==1
    w.capture_workspace();save_project(w.project,w.project_path)
    reopened=load_project(w.project_path)['references'][0]
    assert reopened['group']=='NDWI' and reopened['reference_origin']['name']==path.name
    assert path.name in next(iter(w.reference_buttons.values())).toolTip()
    replacement=path.with_name('renamed_source.vrt');replacement.write_text(path.read_text(encoding='utf-8'),encoding='utf-8')
    w.import_reference_paths([str(replacement)],'NDWI');wait()
    button=next(iter(w.reference_buttons.values()))
    assert button.reference is w.project['references'][0] and replacement.name in button.toolTip()
    button.click();assert w.display_reference is button.reference


def test_unmatched_rasters_are_ignored_even_if_missing(workbench,tmp_path):
    w,app,wait,errors=workbench;base=raster(tmp_path/'rgb'/'tile.tif')
    w.project['images']=[base];w.refresh_images();w.images.setCurrentRow(0)
    reports=[];w.show_import_report=lambda *args:reports.append(args)
    w.import_reference_paths([str(tmp_path/'other.tif')],'VV');wait()
    assert not w.project.get('references') and not reports and not errors
    assert w.statusBar().currentMessage()=='VV · 成功 0 幅 · 跳过 1 项'
    assert '未匹配跳过 1 幅' in w.log.toPlainText()


def test_reference_picker_accepts_vrt_and_tiffs(workbench,tmp_path,monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    from geoforma.dialogs import ReferenceNameDialog
    w,app,wait,errors=workbench;calls=[];path=str(tmp_path/'NDWI.vrt')
    def pick(parent,title,directory,filters):
        assert '*.vrt' in filters and '*.tif' in filters and '*.yaml' not in filters and '*.yml' not in filters
        return [path],filters
    monkeypatch.setattr(QFileDialog,'getOpenFileNames',pick)
    monkeypatch.setattr(ReferenceNameDialog,'exec',lambda dialog:(dialog.setTextValue('NDWI') or 1))
    w.import_reference_paths=lambda files,group:calls.append((files,group))
    w.import_references_dialog();assert calls==[([path],'NDWI')]


def test_suggested_names_and_tooltips_keep_original_list_vrt_and_folder_names(tmp_path):
    from geoforma.reference_images import suggested_reference_name,reference_origin,reference_tooltip
    folder=tmp_path/'Original_NDWI_Long_Folder';image=folder/'tile.tif';vrt=tmp_path/'Original_VRT_Long_Name.vrt';manifest=tmp_path/'Original_List_Long_Name.yaml'
    assert suggested_reference_name([str(image)])==folder.name
    assert suggested_reference_name([str(image),str(vrt)])==vrt.stem
    assert suggested_reference_name([str(image),str(vrt),str(manifest)])==vrt.stem
    for path,metadata,expected in ((image,{},folder.name),(vrt,{},vrt.name),(image,{'source':str(manifest)},manifest.name)):
        origin=reference_origin(path,metadata)
        record=dict(group='新名称',path=str(image),reference_origin=origin)
        assert expected in reference_tooltip(record)
        legacy=dict(group='旧名称',path=str(path),import_list=metadata)
        assert expected in reference_tooltip(legacy)
