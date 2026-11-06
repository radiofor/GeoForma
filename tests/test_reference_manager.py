import copy
import pytest
from pathlib import Path
from PySide6.QtCore import Qt,QPoint,QEvent
from PySide6.QtWidgets import QApplication,QLineEdit,QToolButton,QDialogButtonBox
from PySide6.QtTest import QTest
from shapely.geometry import box,mapping
from geoforma.ui.reference_manager import ReferenceManagerDialog
from geoforma.storage import save_project,load_project
from geoforma.controllers.display import DisplayWorkflow
from geoforma.theme import install_theme
from test_reference_images import raster
from test_workbench import workbench,fake_image


@pytest.fixture(autouse=True)
def reference_dialog_lifetime():
    app=QApplication.instance() or QApplication([]);install_theme(app)
    yield
    for widget in app.topLevelWidgets():
        if isinstance(widget,ReferenceManagerDialog):widget.reject();widget.deleteLater()
    app.sendPostedEvents(None,QEvent.Type.DeferredDelete);app.processEvents()


def test_manager_stages_all_group_members_and_rejects_conflicts():
    app=QApplication.instance() or QApplication([])
    references=[dict(group='NDWI',path='one/tile.tif'),dict(group='ndwi',path='two/other.tif'),dict(group='VV',path='three/tile.tif')]
    before=copy.deepcopy(references);dialog=ReferenceManagerDialog(references)
    assert dialog.groups==[['NDWI',2],['VV',1]]
    for invalid in ('','主影像','vv'):
        dialog.table.item(0,0).setText(invalid);assert dialog.references==before and dialog.message.text()
    dialog.table.item(0,0).setText('水体')
    assert [ref['group'] for ref in dialog.references]==['水体','水体','VV']
    assert dialog.replacement_for(references[1]) is dialog.references[1]
    assert references==before
    dialog.remove();assert dialog.references==[before[2]] and dialog.replacement_for(references[0]) is None
    dialog.remove();assert not dialog.references and dialog.table.rowCount()==0
    dialog.reject();assert references==before


def test_manager_applies_typed_name_on_accept_and_keeps_legacy_names():
    app=QApplication.instance() or QApplication([])
    legacy='旧项目的很长参考类型名称';dialog=ReferenceManagerDialog([dict(group=legacy,path='tile.tif')]);dialog.accept()
    assert dialog.references[0]['group']==legacy
    dialog=ReferenceManagerDialog([dict(group='NDWI',path='tile.tif')]);dialog.show();app.processEvents()
    dialog.table.editItem(dialog.table.item(0,0));app.processEvents();editor=dialog.table.findChild(QLineEdit)
    assert editor is not None and editor.alignment()==Qt.AlignmentFlag.AlignCenter
    editor.selectAll();QTest.keyClicks(editor,'ndvi');dialog.accept()
    assert dialog.result()==dialog.DialogCode.Accepted and dialog.references[0]['group']=='ndvi'


def test_row_icons_target_their_own_group_after_inline_rename():
    app=QApplication.instance() or QApplication([])
    references=[dict(group='NDWI',path='tile.tif'),dict(group='VV',path='tile.tif')]
    dialog=ReferenceManagerDialog(references);dialog.show();app.processEvents()
    assert not hasattr(dialog,'name') and not hasattr(dialog,'rename_button') and not hasattr(dialog,'remove_button')
    assert abs(dialog.table.columnWidth(0)-dialog.table.columnWidth(1))<=1
    assert dialog.table.item(0,0).flags()&Qt.ItemFlag.ItemIsEditable
    assert not dialog.table.item(0,1).flags()&Qt.ItemFlag.ItemIsEditable
    remove=dialog.table.cellWidget(1,2).findChild(QToolButton)
    assert not remove.text() and not remove.icon().isNull()
    dialog.table.item(1,0).setText('VH');assert 'VH' in remove.accessibleName()
    dialog.table.selectRow(0);remove.click()
    assert dialog.references==[references[0]] and dialog.groups==[['NDWI',1]]
    assert references[1]['group']=='VV';dialog.reject()


@pytest.mark.parametrize('target',[0,1])
def test_row_removal_commits_active_name_and_uses_the_updated_group_key(target):
    app=QApplication.instance() or QApplication([])
    references=[dict(group='NDWI',path='tile.tif'),dict(group='VV',path='tile.tif')]
    dialog=ReferenceManagerDialog(references);dialog.show();app.processEvents()
    dialog.table.editItem(dialog.table.item(0,0));app.processEvents();dialog.table.findChild(QLineEdit).setText('Water')
    dialog.table.cellWidget(target,2).findChild(QToolButton).click()
    assert [ref['group'] for ref in dialog.references]==(['VV'] if target==0 else ['Water'])
    assert [ref['group'] for ref in references]==['NDWI','VV']
    dialog.accept()


@pytest.mark.parametrize('mouse',[False,True])
def test_invalid_inline_edit_blocks_ok_until_corrected(mouse):
    app=QApplication.instance() or QApplication([])
    references=[dict(group='NDWI',path='tile.tif'),dict(group='VV',path='tile.tif')]
    dialog=ReferenceManagerDialog(references);dialog.show();app.processEvents()
    dialog.table.editItem(dialog.table.item(0,0));app.processEvents();editor=dialog.table.findChild(QLineEdit)
    editor.setText('vv')
    if mouse:QTest.mouseClick(dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok),Qt.MouseButton.LeftButton)
    else:dialog.accept()
    assert dialog.isVisible() and dialog.references==references and dialog.message.text()
    dialog.table.item(0,0).setText('水体');dialog.accept()
    assert dialog.result()==dialog.DialogCode.Accepted and dialog.references[0]['group']=='水体'
    assert references[0]['group']=='NDWI'


def test_management_updates_active_type_without_render_then_removes_active_safely(workbench,tmp_path,monkeypatch):
    w,app,wait,errors=workbench
    base=raster(tmp_path/'rgb'/'tile.tif');other=raster(tmp_path/'rgb'/'other.tif')
    references=[dict(raster(tmp_path/'NDWI'/'tile.tif'),group='NDWI'),dict(raster(tmp_path/'NDWI'/'other.tif'),group='NDWI'),dict(raster(tmp_path/'VV'/'tile.tif'),group='VV')]
    w.project['images']=[base,other];w.project['references']=references;w.refresh_images();w.images.setCurrentRow(0)
    w.project['labels']=[dict(id='label',image_id=base['id'],annotation_mode='individual',status='confirmed',class_id=1,geometry=mapping(box(10,10,20,20)))]
    w.draft={'points':[[15,15,1]],'box':[10,10,30,30]};w.refresh_labels()
    item=w.view.overlay_records['label'];point=w.view.point_records[0];bounds=w.view.box_item
    w.display_reference=references[0];w.visible_reference=references[0];w.sync_reference_buttons()
    other_button=w.reference_buttons[('vv',references[2]['path'])];generation=w.render_generation;reads=w.raster_renderer.reads;render=[]
    w.request_render=lambda overview=False:render.append(overview)
    def rename(dialog):
        dialog.table.item(0,0).setText('水体');return 1
    monkeypatch.setattr(ReferenceManagerDialog,'exec',rename)
    w.reference_manage_action.trigger()
    assert [ref['group'] for ref in w.project['references']]==['水体','水体','VV']
    assert w.display_reference is w.project['references'][0] and w.visible_reference is w.display_reference
    assert w.reference_buttons[('vv',references[2]['path'])] is other_button
    assert w.render_generation==generation and w.raster_renderer.reads==reads and not render
    assert w.view.overlay_records['label'] is item and w.view.point_records[0] is point and w.view.box_item is bounds
    path=tmp_path/'managed.gfm';save_project(w.project,path)
    assert [ref['group'] for ref in load_project(path)['references']]==['水体','水体','VV']
    monkeypatch.setattr(ReferenceManagerDialog,'exec',lambda dialog:(dialog.remove() or 1))
    w.reference_manage_action.trigger()
    assert [ref['group'] for ref in w.project['references']]==['VV']
    assert w.display_reference is None and w.visible_reference is None and w.main_image_button.isChecked()
    assert render==[True] and w.render_generation==generation+1
    assert w.view.overlay_records['label'] is item and w.view.point_records[0] is point and w.view.box_item is bounds
    assert all(Path(ref['path']).is_file() for ref in references)
    # Real rendering completes the fallback and cannot republish the removed source.
    w.request_render=lambda overview=False:DisplayWorkflow.request_render(w,overview)
    w.request_render(True);wait()
    assert not w.reference_transition_pending and not errors
    save_project(w.project,path);assert [ref['group'] for ref in load_project(path)['references']]==['VV']


def test_management_cancel_and_busy_entry_keep_live_state(workbench,monkeypatch):
    w,app,wait,errors=workbench;image=fake_image('one','tile.tif');reference=dict(image,group='VV')
    w.project['images']=[image];w.project['references']=[reference];w.refresh_images();w.images.setCurrentRow(0)
    revision=w.dirty_revision
    def cancel(dialog):dialog.remove();return 0
    monkeypatch.setattr(ReferenceManagerDialog,'exec',cancel);w.manage_references()
    assert w.project['references']==[reference] and w.dirty_revision==revision
    monkeypatch.setattr(ReferenceManagerDialog,'exec',lambda dialog:(_ for _ in ()).throw(AssertionError('busy dialog')))
    w.task=object()
    try:w.update_controls();assert w.settings_button.isEnabled() and not w.reference_manage_action.isEnabled();w.manage_references()
    finally:w.task=None;w.update_controls()


def test_source_controls_stay_visible_and_eye_precedes_main_at_all_sizes(workbench):
    w,app,wait,errors=workbench;image=fake_image('main','tile.tif');w.project['images']=[image];w.refresh_images();w.images.setCurrentRow(0)
    assert w.main_image_button.isVisible() and w.main_image_button.isChecked()
    w.main_image_button.click();assert w.main_image_button.isChecked()
    references=[dict(image,path=f'{index}/tile.tif',group=str(index),fingerprint=str(index)) for index in range(7)]
    w.project['references']=references;w.sync_reference_buttons()
    for width in (1024,1440,2200):
        w.resize(width,900);QTest.qWait(190);app.processEvents()
        eye=w.visibility_toolbar.widgetForAction(w.raw_view_action)
        assert eye.isVisible() and w.main_image_button.isVisible() and w.settings_button.isVisible()
        assert eye.mapTo(w,QPoint()).x()+eye.width()<=w.main_image_button.mapTo(w,QPoint()).x()
        assert w.settings_button.mapTo(w,QPoint()).x()>w.main_image_button.mapTo(w,QPoint()).x()
        assert w.reference_manage_button.mapTo(w,QPoint()).y()==w.import_reference_button.mapTo(w,QPoint()).y()
        assert w.source_controls.parentWidget().rect().contains(w.source_controls.geometry())
    w.project['references']=[];w.sync_reference_buttons();QTest.qWait(190);app.processEvents()
    holder=w.reference_switch_holder
    assert w.main_image_button.isVisible() and w.main_image_button.isChecked() and holder.isVisible()
    assert holder.left.isVisible() and holder.right.isVisible() and not holder.left.isEnabled() and not holder.right.isEnabled()
