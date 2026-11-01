import pytest
from PySide6.QtCore import Qt,QPoint
from PySide6.QtWidgets import QApplication,QWidget,QVBoxLayout
from PySide6.QtTest import QTest
from geoforma.theme import install_theme
from geoforma.ui.centered_combo import CenteredComboBox


@pytest.fixture
def combo_panel():
    app=QApplication.instance() or QApplication([]);install_theme(app)
    panel=QWidget();panel.resize(min(620,app.primaryScreen().availableGeometry().width()-24),180);layout=QVBoxLayout(panel)
    combo=CenteredComboBox(panel);layout.addWidget(combo)
    panel.show();app.processEvents()
    yield app,panel,combo
    combo.hidePopup();panel.close();panel.deleteLater();app.processEvents()


def test_short_popup_has_readable_equal_rows_and_aligns_with_the_field(combo_panel):
    app,panel,combo=combo_panel;combo.addItems(['CPU · 116 MiB','NVIDIA GPU · 2.42 GiB'])
    app.processEvents();before=combo.geometry();changes=[];combo.currentIndexChanged.connect(changes.append)
    combo.showPopup();app.processEvents();view=combo.view();popup=view.window()
    rows=[view.visualRect(combo.model().index(i,0)) for i in range(2)]
    assert rows[0].height()==rows[1].height()>=32
    assert rows[1].top()>rows[0].bottom()+1
    assert popup.width()==combo.width() and popup.x()==combo.mapToGlobal(QPoint()).x()
    assert popup.y()>=combo.mapToGlobal(QPoint(0,combo.height())).y()
    assert view.viewport().rect().contains(rows[1])
    assert combo.geometry()==before and not changes
    assert all(combo.itemData(i,Qt.ItemDataRole.TextAlignmentRole)==Qt.AlignmentFlag.AlignCenter for i in range(2))


def test_long_popup_stays_on_screen_and_keeps_last_selected_row_visible(combo_panel):
    app,panel,combo=combo_panel;combo.addItems([f'SAM 模型 {i}' for i in range(30)]);combo.setCurrentIndex(29)
    area=panel.screen().availableGeometry();panel.move(area.right()-panel.width()+1,area.bottom()-panel.height()+1)
    app.processEvents();combo.showPopup();app.processEvents();view=combo.view();popup=view.window()
    assert area.contains(popup.geometry())
    assert popup.geometry().bottom()<combo.mapToGlobal(QPoint()).y()
    assert view.verticalScrollBar().maximum()>0
    assert view.viewport().rect().contains(view.visualRect(combo.model().index(29,0)))
    center=view.viewport().mapToGlobal(view.viewport().rect().center()).x()
    assert abs(center-popup.geometry().center().x())<=1


def test_open_cancel_and_reopen_preserve_selection_and_keyboard_can_commit(combo_panel):
    app,panel,combo=combo_panel;combo.addItems(['Small','Base+','Large']);combo.setCurrentIndex(1)
    changes=[];combo.currentIndexChanged.connect(changes.append)
    combo.showPopup();app.processEvents();QTest.keyClick(combo.view(),Qt.Key.Key_Escape);app.processEvents()
    assert combo.currentIndex()==1 and not changes and not combo.view().window().isVisible()
    combo.showPopup();app.processEvents();first=combo.view().window().geometry()
    QTest.keyClick(combo.view(),Qt.Key.Key_Down);QTest.keyClick(combo.view(),Qt.Key.Key_Return);app.processEvents()
    assert combo.currentIndex()==2 and changes==[2]
    combo.showPopup();app.processEvents();assert combo.view().window().geometry()==first


def test_empty_and_disabled_combos_never_create_visible_popups(combo_panel):
    app,panel,combo=combo_panel;combo.showPopup();app.processEvents();assert not combo.view().window().isVisible()
    combo.addItem('CPU');combo.setEnabled(False);combo.showPopup();app.processEvents()
    assert not combo.view().window().isVisible()


def test_reveal_animation_keeps_geometry_fixed_and_stops_on_close(combo_panel,monkeypatch):
    app,panel,combo=combo_panel;combo.addItems(['CPU','NVIDIA GPU'])
    enabled=QApplication.isEffectEnabled(Qt.UIEffect.UI_AnimateCombo)
    monkeypatch.setattr(QApplication,'platformName',lambda:'animation-test')
    monkeypatch.setattr(QApplication,'isEffectEnabled',lambda effect:True)
    try:
        combo.showPopup();app.processEvents();popup=combo.view().window();geometry=popup.geometry()
        assert combo._reveal is not None
        QTest.qWait(130);assert popup.geometry()==geometry and popup.windowOpacity()==1.
        combo.hidePopup();combo.showPopup();combo.hidePopup();QTest.qWait(130)
        assert not popup.isVisible() and popup.windowOpacity()==1.
    finally:QApplication.setEffectEnabled(Qt.UIEffect.UI_AnimateCombo,enabled)
