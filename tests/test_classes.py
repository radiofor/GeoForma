import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from geoforma.classes import next_class_id,referenced_class_ids,validate_classes
from geoforma.domain import new_project
from geoforma.dialogs import ClassesDialog
from geoforma.window import MainWindow
from geoforma.storage import save_project,load_project


def test_custom_names_keep_ids_and_deleted_ids_are_not_reused(tmp_path):
    app=QApplication.instance() or QApplication([])
    project=new_project();assert project['classes']==[{'id':1,'name':'类别 1'}]
    dialog=ClassesDialog(project['classes'],next_class_id(project),set(),1)
    dialog.name_inputs[1].setText('建筑');assert dialog.commit_names();dialog.add();dialog.name_inputs[2].setText('道路');assert dialog.commit_names()
    assert [{k:c[k] for k in ('id','name')} for c in dialog.classes]==[{'id':1,'name':'建筑'},{'id':2,'name':'道路'}]
    assert dialog.classes[1]['color']
    dialog.remove();dialog.add();dialog.name_inputs[3].setText('农田');assert dialog.commit_names()
    assert dialog.classes[-1]['id']==3
    project['classes'],project['next_class_id'],_=dialog.value()
    path=tmp_path/'classes.gfm';save_project(project,path);restored=load_project(path)
    assert restored['classes']==project['classes'] and next_class_id(restored)==4
    dialog.close()


def test_names_validate_and_in_use_classes_cannot_be_removed():
    app=QApplication.instance() or QApplication([])
    label={'class_id':7};used=referenced_class_ids([],[[('id',label,0)]])
    dialog=ClassesDialog([{'id':7,'name':'道路'}],8,used,7)
    assert not dialog.delete_button.isEnabled();dialog.remove();assert len(dialog.classes)==1
    dialog.name_inputs[7].setText(' ');assert not dialog.commit_names();assert dialog.classes[0]['name']=='道路'
    dialog.add();assert len(dialog.classes)==1
    dialog.name_inputs[7].setText('公路');dialog.accept();assert dialog.classes[0]=={'id':7,'name':'公路'}
    for items in [[{'id':0,'name':'背景'}],[{'id':65535,'name':'NoData'}],[{'id':1,'name':'x'},{'id':2,'name':' X '}]]:
        with pytest.raises(ValueError):validate_classes(items)
    dialog.close()


def test_last_category_can_be_deleted_but_unclassified_label_cannot_be_saved(tmp_path):
    app=QApplication.instance() or QApplication([]);w=MainWindow(auto_prepare=False)
    w.autosave_timer.stop();w.autosave=lambda:None;w.project['classes']=[];w.refresh_classes()
    w.draft={'geometry':{'type':'Polygon','coordinates':[[[0,0],[2,0],[2,2],[0,0]]]},'pending':False}
    w.update_controls();assert not w.confirm_button.isEnabled();w.confirm();assert not w.project['labels']
    w.dirty=False;w.close();app.processEvents()


def test_inline_names_and_headers_align_and_invalid_edits_are_not_committed():
    app=QApplication.instance() or QApplication([]);original=[dict(id=1,name='湖泊'),dict(id=2,name='道路')]
    dialog=ClassesDialog(original,3,set(),1);dialog.show();app.processEvents()
    assert [dialog.list.horizontalHeaderItem(i).text() for i in range(3)]==['名称','标签值','符号']
    assert dialog.list.horizontalHeader().defaultAlignment() & Qt.AlignmentFlag.AlignHCenter
    for field in dialog.name_inputs.values():assert field.alignment() & Qt.AlignmentFlag.AlignHCenter
    for field in dialog.value_inputs.values():assert field.alignment() & Qt.AlignmentFlag.AlignHCenter
    field=dialog.name_inputs[2];QTest.mouseClick(field,Qt.MouseButton.LeftButton,pos=field.rect().center())
    assert dialog.list.currentRow()==1
    field.setText('湖泊');dialog.accept()
    assert dialog.result()!=dialog.DialogCode.Accepted and original[1]['name']=='道路'
    assert '重复' in dialog.status.currentMessage() and field.text()=='湖泊'
    field.setText('水体');dialog.accept()
    assert dialog.result()==dialog.DialogCode.Accepted and dialog.classes[1]['name']=='水体' and original[1]['name']=='道路'


def test_delete_invalid_unsaved_row_and_add_unique_default_name():
    app=QApplication.instance() or QApplication([])
    dialog=ClassesDialog([dict(id=1,name='类别 2')],2,set(),1)
    dialog.add();assert dialog.classes[1]['name']=='类别 3'
    dialog.name_inputs[2].setText('');dialog.remove()
    assert dialog.classes==[dict(id=1,name='类别 2')]


def test_pending_name_survives_selecting_another_row():
    app=QApplication.instance() or QApplication([])
    dialog=ClassesDialog([dict(id=1,name='湖泊'),dict(id=2,name='道路')],3,set(),1)
    dialog.show();app.processEvents();first=dialog.name_inputs[1];first.setFocus();first.setText('冰川湖')
    QTest.mouseClick(dialog.name_inputs[2],Qt.MouseButton.LeftButton);app.processEvents()
    assert dialog.list.currentRow()==1 and dialog.classes[0]['name']=='冰川湖'
    dialog.add();dialog.accept()
    assert dialog.classes[0]['name']=='冰川湖' and len(dialog.classes)==3
