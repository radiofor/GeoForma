from PySide6.QtCore import Qt,QObject,QEvent,QPoint,QRectF
import pytest
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication,QWidget,QVBoxLayout,QPushButton,QToolButton,QCheckBox,QComboBox,QDoubleSpinBox,QTabBar,QStyle,QStyleOptionSpinBox
from PySide6.QtTest import QTest
from geoforma.theme import install_theme
from geoforma.ui.button_feedback import feedback_kind,PressFeedback
from test_workbench import workbench,fake_image


def test_feedback_is_safe_to_paint_during_parent_child_event():
    app=QApplication.instance() or QApplication([])
    button=QPushButton('test');instances=[];errors=[];paints=[]

    class ReentrantFeedback(PressFeedback):
        def __new__(cls,*args):
            instance=super().__new__(cls);instances.append(instance);return instance

    class ChildEventSpy(QObject):
        def eventFilter(self,obj,event):
            if event.type()==QEvent.Type.ChildAdded:
                paints.append(True)
                try:instances[-1].paintEvent(None)
                except Exception as error:errors.append(error)
            return False

    spy=ChildEventSpy();button.installEventFilter(spy)
    overlay=ReentrantFeedback(button)
    assert paints and not errors
    assert overlay.strength==0 and not overlay.hovered
    button.removeEventFilter(spy);button.deleteLater()


def test_feedback_covers_mouse_keyboard_programmatic_buttons_without_moving_them():
    app=QApplication.instance() or QApplication([]);install_theme(app)
    panel=QWidget();layout=QVBoxLayout(panel);buttons=[]
    for role in ('normal','primary','danger','toggle','navigation','dialog'):
        button=QPushButton(role);button.setProperty('feedback',role);button.setCheckable(role=='toggle');layout.addWidget(button);buttons.append(button)
    check=QCheckBox('自动应用');layout.addWidget(check);buttons.append(check)
    panel.show();app.processEvents();assert hasattr(app,'_geoforma_button_feedback')
    geometry=[button.geometry() for button in buttons];calls=[]
    buttons[0].clicked.connect(lambda:calls.append('mouse'))
    for button in buttons:
        before=button.grab().toImage();QTest.mousePress(button,Qt.MouseButton.LeftButton);app.processEvents()
        overlay=button._geoforma_feedback
        assert overlay.isVisible() and overlay.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        assert overlay.focusPolicy()==Qt.FocusPolicy.NoFocus and button.grab().toImage()!=before
        QTest.mouseRelease(button,Qt.MouseButton.LeftButton)
    assert calls==['mouse'] and [button.geometry() for button in buttons]==geometry
    buttons[0].setFocus();QTest.keyPress(buttons[0],Qt.Key.Key_Space);assert buttons[0]._geoforma_feedback.isVisible()
    QTest.keyRelease(buttons[0],Qt.Key.Key_Space)
    paints=[];ack=[]
    class PaintSpy(QObject):
        def eventFilter(self,obj,event):
            if event.type()==QEvent.Type.Paint:paints.append(True)
            return False
    spy=PaintSpy();buttons[1]._geoforma_feedback.installEventFilter(spy)
    buttons[1].clicked.connect(lambda:ack.append(bool(paints)))
    buttons[1].click();assert buttons[1]._geoforma_feedback.isVisible() and ack==[True]
    buttons[2].setEnabled(False);QTest.mouseClick(buttons[2],Qt.MouseButton.LeftButton);assert buttons[2]._geoforma_feedback.strength==0
    QTest.mouseMove(panel,QPoint(1,1))
    QTest.qWait(230);assert all(not button._geoforma_feedback.hovered and button._geoforma_feedback.strength==0 for button in buttons)
    assert [button.geometry() for button in buttons]==geometry;panel.close()


def test_feedback_uses_action_roles_and_handles_tab_combo_and_spin_controls():
    app=QApplication.instance() or QApplication([]);install_theme(app);panel=QWidget();layout=QVBoxLayout(panel)
    action=QAction('删除',panel);action.setProperty('feedback','danger');button=QToolButton();button.setDefaultAction(action);layout.addWidget(button)
    assert feedback_kind(button)=='danger'
    tabs=QTabBar();tabs.addTab('逐个标注');tabs.addTab('全图分割');layout.addWidget(tabs)
    combo=QComboBox();combo.addItems(['湖泊','道路']);layout.addWidget(combo)
    spin=QDoubleSpinBox();layout.addWidget(spin);panel.show();app.processEvents()
    QTest.mouseClick(tabs,Qt.MouseButton.LeftButton,pos=tabs.tabRect(1).center())
    assert tabs.currentIndex()==1 and tabs._geoforma_feedback.isVisible()
    QTest.mousePress(combo,Qt.MouseButton.LeftButton);assert not hasattr(combo,'_geoforma_feedback');combo.hidePopup()
    option=QStyleOptionSpinBox();spin.initStyleOption(option)
    rect=spin.style().subControlRect(QStyle.ComplexControl.CC_SpinBox,option,QStyle.SubControl.SC_SpinBoxUp,spin)
    QTest.mouseClick(spin,Qt.MouseButton.LeftButton,pos=rect.center())
    assert spin.value()==1 and spin._geoforma_feedback.isVisible()
    panel.close()


def test_hover_highlights_buttons_with_local_styles_without_clicking_or_resizing(hover_move):
    app=QApplication.instance() or QApplication([]);install_theme(app);panel=QWidget();layout=QVBoxLayout(panel)
    plain=QPushButton('新增');selected=QToolButton();selected.setText('主影像');selected.setCheckable(True);selected.setChecked(True)
    selected.setStyleSheet('QToolButton{background:white;border:1px solid #ccdce2;}')
    disabled=QPushButton('暂不可用');disabled.setEnabled(False)
    buttons=[plain,selected,disabled];calls=[]
    for button in buttons:layout.addWidget(button);button.clicked.connect(lambda:calls.append(True))
    panel.show();app.processEvents();hover_move(panel,QPoint(1,1))
    for button in buttons:
        before=button.grab().toImage();geometry=button.geometry()
        hover_move(button)
        assert button._geoforma_feedback.hovered and button._geoforma_feedback.isVisible()
        assert button.grab().toImage()!=before and button.geometry()==geometry
        assert selected.isChecked() and not calls
        hover_move(panel,QPoint(1,1));assert not button._geoforma_feedback.hovered and button._geoforma_feedback.strength==0
    panel.close();panel.deleteLater()


@pytest.mark.parametrize('direction',[Qt.LayoutDirection.LeftToRight,Qt.LayoutDirection.RightToLeft])
@pytest.mark.parametrize('height',[18,22,32])
def test_checkbox_highlight_stroke_fits_inside_the_control(direction,height,hover_move):
    app=QApplication.instance() or QApplication([]);install_theme(app);panel=QWidget();layout=QVBoxLayout(panel)
    check=QCheckBox('单一多边形');check.setLayoutDirection(direction);check.setFixedHeight(height);layout.addWidget(check)
    panel.show();app.processEvents();geometry=check.geometry()
    hover_move(check);overlay=check._geoforma_feedback
    assert overlay.isVisible() and QRectF(overlay.rect()).contains(overlay.feedback_rect().adjusted(-1,-1,1,1))
    QTest.mousePress(check,Qt.MouseButton.LeftButton);app.processEvents()
    assert QRectF(overlay.rect()).contains(overlay.feedback_rect().adjusted(-1,-1,1,1)) and check.geometry()==geometry
    QTest.mouseRelease(check,Qt.MouseButton.LeftButton);panel.close();panel.deleteLater()


def test_raster_row_hover_highlights_without_changing_current_image(workbench,hover_move):
    w,app,wait,errors=workbench;w.project['images']=[fake_image('one'),fake_image('two')]
    w.refresh_images();w.images.setCurrentRow(0);app.processEvents()
    viewport=w.images.viewport();hover_move(w.view.viewport(),QPoint(10,10))
    assert w.images.hasMouseTracking()
    for row in (0,1):
        idle=viewport.grab().toImage();hover_move(viewport,w.images.visualItemRect(w.images.item(row)).center())
        assert viewport.grab().toImage()!=idle
        assert w.images.currentRow()==0 and w.image is w.project['images'][0]
        hover_move(w.view.viewport(),QPoint(10,10))
    assert not errors
