import copy
import pytest
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication,QDialogButtonBox
from PySide6.QtTest import QTest
from geoforma.dialogs import ReferenceNameDialog
from geoforma.reference_images import reference_group_name
from test_workbench import workbench,fake_image


def test_name_dialog_keeps_full_focused_selection_and_truncates_only_committed_value():
    app=QApplication.instance() or QApplication([]);dialog=ReferenceNameDialog('a very long folder name')
    field=dialog.field;ok=dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok)
    dialog.show();QTest.qWait(10);app.processEvents()
    assert field.hasFocus() and field.textCursor().selectedText()=='a very long folder name'
    assert dialog.textValue()=='a very long folder name' and dialog.value()=='a very l'
    field.setText('123456789');assert dialog.textValue()=='123456789' and dialog.value()=='12345678' and ok.isEnabled()
    field.setText('主影像');assert not ok.isEnabled()
    field.setText('   ');assert not ok.isEnabled()
    field.setText('NDWI');assert ok.isEnabled()
    dialog.close();app.processEvents()


def test_long_reference_names_wrap_without_hiding_text():
    app=QApplication.instance() or QApplication([]);name='完整参考来源名称需要全部显示_'*12
    dialog=ReferenceNameDialog(name);dialog.show();QTest.qWait(10);app.processEvents()
    assert dialog.textValue()==name and dialog.field.textCursor().selectedText()==name
    assert dialog.field.height()>38 and dialog.field.verticalScrollBar().maximum()==0
    assert dialog.value()==name[:8] and dialog.field.horizontalScrollBar().maximum()==0
    dialog.reject()


@pytest.mark.parametrize('name',['123456789','主影像','ND\nWI',''])
def test_invalid_reference_names_do_not_start_import(workbench,monkeypatch,name):
    w,app,wait,errors=workbench;image=fake_image('main','tile.tif');w.project['images']=[image]
    monkeypatch.setattr('geoforma.controllers.references.inspect_source',lambda *args:pytest.fail('Invalid name must be rejected before raster IO'))
    w.import_reference_paths(['tile.tif'],name)
    assert w.task is None and not w.project.get('references') and not errors
    assert w.statusBar().currentMessage()
    with pytest.raises(ValueError):reference_group_name(name)


def test_equal_button_sizes_and_legacy_long_names_keep_original_records(workbench,hover_move):
    w,app,wait,errors=workbench;image=fake_image('main','tile.tif');image['ready']=True
    names=['VV','NDWI','很长的旧参考类型名称','NDVI']
    references=[dict(image,path=f'{i}/tile.tif',group=name,fingerprint=str(i)) for i,name in enumerate(names)]
    before=copy.deepcopy(references);w.project['images']=[image];w.project['references']=references
    w.refresh_images();w.images.setCurrentRow(0);QTest.qWait(180);app.processEvents()
    buttons=[w.main_image_button]+[w.reference_switches.layout().itemAt(i).widget() for i in range(4)]
    assert buttons[0].text()=='主影像'
    assert {(button.width(),button.height()) for button in buttons}=={(96,30)}
    assert names[2] in buttons[3].toolTip() and len(buttons[3].text())<=8 and '…' in buttons[3].text()
    assert w.reference_switch_holder.viewport().height()>=30
    assert references==before
    for button in buttons[:2]:
        hover_move(w.view.viewport(),QPoint(10,10));idle=button.grab().toImage()
        geometry=button.geometry();hover_move(button)
        assert button._geoforma_feedback.hovered and button.grab().toImage()!=idle
        assert button.geometry()==geometry and w.display_reference is None
    assert references==before
    for reference in references+[None]:
        w.switch_reference(reference)
        assert {(button.width(),button.height()) for button in buttons}=={(96,30)}
    assert not errors
