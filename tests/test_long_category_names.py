"""Names stay intact while compact fields, expanded views and numbers fit."""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from geoforma.dialogs import ClassesDialog
from test_reshape import workbench,raster_image


def test_large_serials_have_room_without_changing_the_table_width(workbench):
    w,app,_=workbench;w.show();app.processEvents();table=w.labels_table;width=table.width()
    for count in (9,999,99999,123456789012):
        table.sync_serial_width(count);app.processEvents()
        assert table.columnWidth(0)>=table.fontMetrics().horizontalAdvance(str(count))+16
        assert table.width()==width
    table.sync_serial_width(1);assert table.columnWidth(0)==48
    from geoforma.ui.label_table import LabelTable
    independent=LabelTable()
    independent.setRowCount(100000)
    assert independent.columnWidth(0)>=independent.fontMetrics().horizontalAdvance('100000')+16
    independent.setRowCount(1);assert independent.columnWidth(0)==48
    independent.deleteLater();app.processEvents()


@pytest.mark.parametrize('name',['冰川湖泊与周边季节性积水区域分类名称'*4,'Long_Category_Name_Without_Spaces_'*150],ids=['long_chinese','unbroken_english'])
def test_long_category_popup_expands_without_losing_text(workbench,name):
    w,app,tmp=workbench;w.project['classes']=[{'id':1,'name':name},{'id':2,'name':'普通类别'}]
    w.refresh_classes();w.refresh_labels();w.resize(1280,900);w.show();app.processEvents()
    for combo in (w.classes,):
        window_size=w.size();field_width=combo.width();combo.showPopup();app.processEvents()
        view=combo.view();popup=view.window();area=combo.screen().availableGeometry()
        assert popup.width()>field_width and area.contains(popup.geometry())
        assert combo.itemText(0)==name and combo.currentText()==name and w.size()==window_size
        assert view.textElideMode()==Qt.TextElideMode.ElideNone
        if combo.fontMetrics().horizontalAdvance(name)>area.width():
            bar=view.horizontalScrollBar();assert bar.maximum()>0 and bar.value()==0
            start=view.visualRect(combo.model().index(0,0));bar.setValue(bar.maximum());app.processEvents()
            end=view.visualRect(combo.model().index(0,0))
            assert end.left()<start.left() and end.right()<=view.viewport().rect().right()
            assert view.visualRect(combo.model().index(1,0)).bottom()<=view.viewport().rect().bottom()
        popup.grab().save(str(tmp/('category_popup_top.png' if combo is w.classes else 'category_popup_row.png')))
        combo.hidePopup()
    item=w.category_buttons.items[1]
    assert item.text()==name and item.toolTip()==name
    assert w.labels_table.item(0,1).text()==name and w.labels_table.item(0,1).toolTip()==name


def test_long_category_buttons_keyboard_selection_can_be_undone(workbench):
    w,app,_=workbench;name='Long_Category_'*100
    w.project['classes']=[{'id':1,'name':name},{'id':2,'name':'普通类别'}];w.refresh_classes();w.refresh_labels();w.show();app.processEvents()
    w.select_label('target');buttons=w.category_buttons;buttons.setCurrentItem(buttons.items[2]);buttons.setFocus()
    QTest.keyClick(buttons,Qt.Key.Key_Return);app.processEvents()
    assert w.project['labels'][0]['class_id']==2
    w.undo_context();assert w.project['labels'][0]['class_id']==1 and buttons.active==1


def test_class_editor_can_show_and_preserve_names_beyond_line_edit_default(workbench):
    w,app,tmp=workbench;name='长类别名称_中文_English_1234567890_'*1600
    dialog=ClassesDialog([{'id':1,'name':name,'value':65534},{'id':2,'name':'短名称'}],3,set(),1,w)
    dialog.resize(480,400);dialog.show();app.processEvents()
    assert dialog.name_inputs[1].text()==name and dialog.name_inputs[1].cursorPosition()==0
    field=dialog.value_inputs[1]
    assert field.width()>=field.fontMetrics().horizontalAdvance('65534')+38
    updated=name+'末尾修改';dialog.name_inputs[1].setText(updated);assert dialog.commit_names()
    assert dialog.classes[0]['name']==updated and dialog.name_inputs[1].text()==updated
    dialog.grab().save(str(tmp/'long_category_editor.png'))
    dialog.close();app.processEvents()
