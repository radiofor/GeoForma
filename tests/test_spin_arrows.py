import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication,QStyle,QStyleOptionSpinBox
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from geoforma.window import MainWindow


def test_visible_spin_arrows_change_values():
    app=QApplication.instance() or QApplication([]);w=MainWindow(auto_prepare=False);w.autosave=lambda:None
    w.show();w.smooth_value.setValue(2);app.processEvents()
    spin=w.smooth_value;option=QStyleOptionSpinBox();spin.initStyleOption(option)
    up=spin.style().subControlRect(QStyle.ComplexControl.CC_SpinBox,option,QStyle.SubControl.SC_SpinBoxUp,spin)
    down=spin.style().subControlRect(QStyle.ComplexControl.CC_SpinBox,option,QStyle.SubControl.SC_SpinBoxDown,spin)
    assert not up.isEmpty() and not down.isEmpty()
    QTest.mouseClick(spin,Qt.MouseButton.LeftButton,pos=up.center());assert spin.value()==2+spin.singleStep()
    QTest.mouseClick(spin,Qt.MouseButton.LeftButton,pos=down.center());assert spin.value()==2
    assert w.editor_scroll.widget().width()<=w.editor_scroll.viewport().width()
    w.dirty=False;w.close();app.processEvents()
