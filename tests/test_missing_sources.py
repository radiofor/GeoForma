import copy,shutil
from pathlib import Path
import pytest
from geoforma.domain import new_project
from geoforma.missing_sources import missing_sources,relink_source,remove_source
from geoforma.storage import save_project,load_project
from test_project_autosave import automatic_project,until
from test_reshape import raster_image


def test_relink_checks_metadata_and_invalidates_cache(tmp_path,raster_image):
    image=copy.deepcopy(raster_image);image['ready']=True;image['prepared_cache_revision']='old'
    new=tmp_path/'moved.tif';shutil.copy2(image['path'],new);Path(image['path']).unlink()
    assert missing_sources({'images':[image]})
    relink_source(image,new)
    assert image['path']==str(new.resolve()) and not image['ready'] and 'prepared_cache_revision' not in image
    wrong=copy.deepcopy(image);wrong['width']+=1
    with pytest.raises(ValueError):relink_source(wrong,new)
    assert wrong['path']==image['path']


def test_remove_image_clears_its_labels_and_history_only(tmp_path,raster_image):
    image=copy.deepcopy(raster_image);other=copy.deepcopy(image);other['id']='other'
    project={'images':[image,other],'labels':[{'id':'a','image_id':image['id']},{'id':'b','image_id':'other'}],
             'history':{'schema':1},'workspace':{'image_id':image['id'],'draft':{},'reshape':{},'auto_apply':True}}
    remove_source(project,'images',image)
    assert project['images']==[other] and [l['id'] for l in project['labels']]==['b']
    assert 'history' not in project and project['workspace']=={'auto_apply':True}


def test_relink_rejects_duplicate_project_source_without_changes(tmp_path,raster_image):
    image=copy.deepcopy(raster_image);other=copy.deepcopy(image);other['id']='other'
    image['path']=str(tmp_path/'missing.tif');before=copy.deepcopy(image)
    with pytest.raises(ValueError,match='已存在'):
        relink_source(image,other['path'],{'images':[image,other]},'images')
    assert image==before


def test_relink_keeps_reference_matching_stable(tmp_path,raster_image):
    image=copy.deepcopy(raster_image);image['path']=str(tmp_path/'old'/'source.tif')
    reference=copy.deepcopy(image);reference['group']='参考'
    project={'images':[image],'references':[reference]}
    renamed=tmp_path/'renamed.tif';shutil.copy2(raster_image['path'],renamed)
    with pytest.raises(ValueError,match='参考影像'):
        relink_source(image,renamed,project,'images')
    with pytest.raises(ValueError,match='文件名'):
        relink_source(reference,renamed,project,'references')
    replacement=tmp_path/'new'/'source.tif';replacement.parent.mkdir();shutil.copy2(raster_image['path'],replacement)
    relink_source(image,replacement,project,'images')
    assert image['path']==str(replacement.resolve())


def test_open_relinks_missing_image_and_saves_new_path(automatic_project,monkeypatch,raster_image):
    w,app,tmp=automatic_project;project=new_project();project['images']=[copy.deepcopy(raster_image)]
    path=tmp/'saved.gfm';save_project(project,path)
    new=tmp/'moved.tif';shutil.copy2(raster_image['path'],new);Path(raster_image['path']).unlink()
    def resolve(project):
        kind,image=missing_sources(project)[0];relink_source(image,new);return True
    monkeypatch.setattr(w,'resolve_missing_project_sources',resolve)
    assert w.request_project_open(path)
    until(app,lambda:w.loading_task is None and w.project_transition is None)
    until(app,lambda:not w.dirty and w.autosave_task is None)
    assert w.project['images'][0]['path']==str(new.resolve())
    assert load_project(path)['images'][0]['path']==str(new.resolve())


def test_cancel_missing_image_keeps_project_and_file(automatic_project,monkeypatch,raster_image):
    w,app,tmp=automatic_project;project=new_project();project['images']=[copy.deepcopy(raster_image)]
    path=tmp/'saved.gfm';save_project(project,path);before=path.read_bytes();Path(raster_image['path']).unlink()
    old=w.project;monkeypatch.setattr(w,'resolve_missing_project_sources',lambda project:None)
    assert w.request_project_open(path)
    until(app,lambda:w.loading_task is None and w.project_transition is None)
    assert w.project is old and path.read_bytes()==before


def test_invalid_relink_error_appears_inside_reopened_choice_dialog(automatic_project,monkeypatch,raster_image):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication,QFileDialog,QMessageBox
    w,app,tmp=automatic_project;project=new_project();image=copy.deepcopy(raster_image)
    image['path']=str(tmp/'missing.tif');project['images']=[image]
    monkeypatch.setattr(QFileDialog,'getOpenFileName',lambda *args:(str(tmp/'not-a-raster.tif'),''))
    def denied(*args):raise PermissionError(13,'Access denied')
    monkeypatch.setattr('geoforma.missing_sources.relink_source',denied)
    observed=[]
    def choose_location():
        box=QApplication.activeModalWidget();assert isinstance(box,QMessageBox)
        next(button for button in box.buttons() if button.text()=='选择新位置').click()
    def check_error_and_cancel():
        box=QApplication.activeModalWidget();assert isinstance(box,QMessageBox)
        toast=box._error_toast
        observed.append((toast.label.isVisible(),toast.label.parent() is box,toast.label.text(),toast.timer.interval()))
        next(button for button in box.buttons() if button.text()=='取消打开').click()
    def safety_close():
        box=QApplication.activeModalWidget()
        if isinstance(box,QMessageBox):box.reject()
    safety=QTimer(w);safety.setSingleShot(True);safety.timeout.connect(safety_close);safety.start(5000)
    QTimer.singleShot(0,choose_location);QTimer.singleShot(100,check_error_and_cancel)
    try:assert w.resolve_missing_project_sources(project) is None
    finally:safety.stop()
    assert len(observed)==1 and observed[0][0:2]==(True,True)
    assert '无法使用所选数据' in observed[0][2] and observed[0][3]==2000
    assert '没有访问权限' in observed[0][2] and 'PermissionError' in w.log.toPlainText()


def test_invalid_band_range_uses_nonblocking_error(automatic_project,monkeypatch,raster_image):
    w,app,_=automatic_project;w.image=raster_image;w.project['images']=[raster_image]
    monkeypatch.setattr('geoforma.controllers.images.BandsDialog',lambda *args:object())
    monkeypatch.setattr('geoforma.controllers.images.dialog_result',lambda *args:(True,([1,2,3],[(5,5)]*3,1,None)))
    w.configure_bands()
    assert '最大值必须大于最小值' in w.statusBar()._error_toast.label.text()


def test_export_without_labels_uses_status_bar(automatic_project,raster_image):
    w,app,_=automatic_project;w.image=raster_image;w.project['images']=[raster_image]
    w.project['labels']=[];w.export()
    assert w.statusBar().currentMessage()=='当前影像没有可导出的标签。'


def test_open_rejects_removed_candidate_labels_without_modifying_project(automatic_project,raster_image):
    from shapely.geometry import box,mapping
    w,app,tmp=automatic_project;project=new_project();project['images']=[copy.deepcopy(raster_image)]
    image_id=raster_image['id'];geometry=mapping(box(10,10,20,20))
    project['labels']=[{'id':'confirmed','image_id':image_id,'status':'confirmed','class_id':1,'geometry':geometry},
                       {'id':'obsolete','image_id':image_id,'status':'candidate','class_id':None,'geometry':geometry}]
    path=tmp/'old.gfm';save_project(project,path);before=path.read_bytes();previous=w.project
    assert not w.open_project(path)
    assert w.project is previous and path.read_bytes()==before
