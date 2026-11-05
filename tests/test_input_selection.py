"""Editable controls share first-click selection and ordinary subsequent clicks."""
import pytest
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QDialog,QLineEdit,QPlainTextEdit,QPushButton,QSpinBox,QVBoxLayout,QStyle,QStyleOptionSpinBox
from geoforma.ui.input_selection import install_input_selection
from geoforma.dialogs import ClassesDialog


@pytest.fixture
def input_dialog():
    app=QApplication.instance() or QApplication([]);install_input_selection(app)
    dialog=QDialog();layout=QVBoxLayout(dialog)
    button=QPushButton('focus');line=QLineEdit('abcdef');spin=QSpinBox();spin.setRange(0,10000);spin.setValue(1234)
    multiline=QPlainTextEdit();multiline.setPlainText('long reference name')
    for widget in (button,line,spin,multiline):layout.addWidget(widget)
    dialog.show();dialog.activateWindow();button.setFocus();app.processEvents()
    yield app,dialog,button,line,spin,multiline
    dialog.close();dialog.deleteLater();app.processEvents()


def test_first_click_selects_all_then_second_positions_cursor(input_dialog):
    app,dialog,button,line,spin,multiline=input_dialog
    QTest.mouseClick(line,Qt.MouseButton.LeftButton,pos=line.rect().center());app.processEvents()
    assert line.selectedText()=='abcdef'
    QTest.mouseClick(line,Qt.MouseButton.LeftButton,pos=QPoint(8,line.height()//2));app.processEvents()
    assert not line.hasSelectedText() and line.cursorPosition()<len(line.text())
    button.setFocus();app.processEvents()
    QTest.mouseClick(spin.lineEdit(),Qt.MouseButton.LeftButton,pos=spin.lineEdit().rect().center());app.processEvents()
    assert spin.lineEdit().selectedText()=='1234'
    QTest.mouseClick(spin.lineEdit(),Qt.MouseButton.LeftButton,pos=QPoint(8,spin.lineEdit().height()//2));app.processEvents()
    assert not spin.lineEdit().hasSelectedText()
    button.setFocus();app.processEvents()
    QTest.mouseClick(multiline.viewport(),Qt.MouseButton.LeftButton,pos=QPoint(10,10));app.processEvents()
    assert multiline.textCursor().selectedText()=='long reference name'
    QTest.mouseClick(multiline.viewport(),Qt.MouseButton.LeftButton,pos=QPoint(10,10));app.processEvents()
    assert not multiline.textCursor().hasSelection()


def test_keyboard_focus_and_edit_after_selection(input_dialog):
    app,dialog,button,line,spin,multiline=input_dialog
    QTest.keyClick(button,Qt.Key.Key_Tab);app.processEvents()
    assert line.hasFocus() and line.selectedText()=='abcdef'
    QTest.keyClicks(line,'xyz');assert line.text()=='xyz'
    QTest.mouseClick(line,Qt.MouseButton.LeftButton,pos=QPoint(8,line.height()//2));app.processEvents()
    assert not line.hasSelectedText()


def test_category_value_arrows_still_adjust_and_validate():
    app=QApplication.instance() or QApplication([]);install_input_selection(app)
    dialog=ClassesDialog([dict(id=1,name='湖泊',value=1),dict(id=2,name='道路',value=10)],3,set(),1)
    dialog.show();dialog.activateWindow();app.processEvents();spin=dialog.value_inputs[1]
    option=QStyleOptionSpinBox();spin.initStyleOption(option)
    up=spin.style().subControlRect(QStyle.ComplexControl.CC_SpinBox,option,QStyle.SubControl.SC_SpinBoxUp,spin)
    down=spin.style().subControlRect(QStyle.ComplexControl.CC_SpinBox,option,QStyle.SubControl.SC_SpinBoxDown,spin)
    assert not up.isEmpty() and not down.isEmpty()
    QTest.mouseClick(spin,Qt.MouseButton.LeftButton,pos=up.center());app.processEvents()
    assert spin.value()==2 and dialog.classes[0]['value']==2
    QTest.mouseClick(spin,Qt.MouseButton.LeftButton,pos=down.center());app.processEvents()
    assert spin.value()==1 and dialog.classes[0]['value']==1
    spin.setValue(9);QTest.mouseClick(spin,Qt.MouseButton.LeftButton,pos=up.center());app.processEvents()
    assert spin.value()==9 and '唯一' in dialog.status.currentMessage()
    dialog.close();dialog.deleteLater();app.processEvents()


def test_category_name_click_replaces_text_then_second_click_inserts():
    app=QApplication.instance() or QApplication([]);install_input_selection(app)
    dialog=ClassesDialog([dict(id=1,name='Lake'),dict(id=2,name='Road')],3,set(),1)
    dialog.show();dialog.activateWindow();dialog.add_button.setFocus();app.processEvents()
    name=dialog.name_inputs[2];QTest.mouseClick(name,Qt.MouseButton.LeftButton,pos=name.rect().center())
    assert name.selectedText()=='Road' and dialog.list.currentRow()==1
    QTest.keyClicks(name,'River');assert name.text()=='River'
    QTest.mouseClick(name,Qt.MouseButton.LeftButton,pos=QPoint(8,name.height()//2));app.processEvents()
    assert not name.hasSelectedText();QTest.keyClicks(name,'X')
    dialog.accept();assert dialog.classes[1]['name']=='XRiver'
    dialog.deleteLater();app.processEvents()
