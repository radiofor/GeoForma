import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtWidgets import QApplication
from geoforma.classes import next_class_id,referenced_class_ids,validate_classes
from geoforma.domain import new_project
from geoforma.dialogs import ClassesDialog
from geoforma.window import MainWindow
from geoforma.storage import save_project,load_project


def test_custom_names_keep_ids_and_deleted_ids_are_not_reused(tmp_path):
    app=QApplication.instance() or QApplication([])
    project=new_project();assert project['classes']==[{'id':1,'name':'类别 1'}]
    dialog=ClassesDialog(project['classes'],next_class_id(project),set(),1)
    dialog.name.setText('建筑');dialog.rename();dialog.name.setText('道路');dialog.add()
    assert [{k:c[k] for k in ('id','name')} for c in dialog.classes]==[{'id':1,'name':'建筑'},{'id':2,'name':'道路'}]
    assert dialog.classes[1]['color']
    dialog.remove();dialog.name.setText('农田');dialog.add()
    assert dialog.classes[-1]['id']==3
    project['classes'],project['next_class_id'],_=dialog.value()
    path=tmp_path/'classes.geoforma.json';save_project(project,path);restored=load_project(path)
    assert restored['classes']==project['classes'] and next_class_id(restored)==4
    dialog.close()


def test_names_validate_and_in_use_classes_cannot_be_removed():
    app=QApplication.instance() or QApplication([])
    label={'class_id':7};used=referenced_class_ids([],[[('id',label,0)]])
    dialog=ClassesDialog([{'id':7,'name':'道路'}],8,used,7)
    assert not dialog.delete_button.isEnabled();dialog.remove();assert len(dialog.classes)==1
    dialog.name.setText('道路');dialog.add();assert len(dialog.classes)==1
    dialog.name.setText(' ');dialog.rename();assert dialog.classes[0]['name']=='道路'
    dialog.name.setText('公路');dialog.accept();assert dialog.classes[0]=={'id':7,'name':'公路'}
    for items in [[{'id':0,'name':'背景'}],[{'id':65535,'name':'NoData'}],[{'id':1,'name':'x'},{'id':2,'name':' X '}]]:
        with pytest.raises(ValueError):validate_classes(items)
    dialog.close()


def test_last_category_can_be_deleted_but_unclassified_label_cannot_be_saved(tmp_path):
    app=QApplication.instance() or QApplication([]);w=MainWindow(auto_prepare=False)
    w.autosave_timer.stop();w.autosave=lambda:None;w.project['classes']=[];w.refresh_classes()
    w.draft={'geometry':{'type':'Polygon','coordinates':[[[0,0],[2,0],[2,2],[0,0]]]},'pending':False}
    w.update_controls();assert not w.confirm_button.isEnabled();w.confirm();assert not w.project['labels']
    w.dirty=False;w.close();app.processEvents()
