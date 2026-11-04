"""Panel geometry remains stable across text updates, task activity, and editing modes."""
from PySide6.QtCore import QPoint,Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel,QPushButton,QToolButton,QComboBox
from shapely.geometry import box,mapping

from test_workbench import workbench,fake_image


def settle(app):
    for _ in range(5):app.processEvents()


def rectangles(w):
    names=('mode_settings','editor_group','labels_table',
           'zoom_button','review_navigation','export_group','image_scroll','model_button',
           'images','image_info','state_label','context_status')
    return {name:(getattr(w,name).mapTo(w,QPoint()).toTuple(),getattr(w,name).size().toTuple()) for name in names}


def test_model_selector_and_device_share_one_stable_row(workbench):
    from geoforma.model_catalog import MODELS
    w,app,wait,errors=workbench;w.resize(1440,900)
    w.resizeDocks([w.image_dock],[280],Qt.Orientation.Horizontal);settle(app)
    button=w.model_button;device=w.model_runtime
    assert button.parentWidget() is device.parentWidget()
    assert not button.icon().isNull()
    assert button.icon_rect().right()==button.width()-7
    assert button.geometry().right()<device.geometry().left()
    assert button.height()==device.height()==32
    assert button.width()>=device.width()
    assert abs(button.geometry().center().y()-device.geometry().center().y())<=1
    geometry=(button.geometry(),device.geometry())
    for spec in MODELS:
        w.project['model'].update(backend=spec['backend'],variant=spec['variant'],device='cuda')
        w.runtime_status=None;w.update_controls();settle(app)
        assert button.fontMetrics().horizontalAdvance(button.text())+button.iconSize().width()+12<=button.width()
        assert '…' not in device._display_text
        assert (button.geometry(),device.geometry())==geometry
    w.resizeDocks([w.image_dock],[400],Qt.Orientation.Horizontal);settle(app)
    if button.parentWidget().width()>=320:assert button.width()>device.width()
    assert not errors


def test_model_selector_icon_keeps_the_configuration_clickable(workbench,monkeypatch):
    from geoforma.controllers import models
    from geoforma.dialogs import ModelDialog
    w,app,wait,errors=workbench;opened=[]
    def cancel(dialog,extract):
        opened.append((isinstance(dialog,ModelDialog),dialog.parent() is w));dialog.deleteLater()
        return False,None
    monkeypatch.setattr(models,'dialog_result',cancel)
    image=w.model_button.grab().toImage();ratio=image.devicePixelRatio();rect=w.model_button.icon_rect()
    pixels=(image.pixelColor(x,y) for y in range(int(rect.top()*ratio),int((rect.bottom()+1)*ratio))
            for x in range(int(rect.left()*ratio),int((rect.right()+1)*ratio)))
    assert any(max(color.red(),color.green(),color.blue())<180 for color in pixels)
    QTest.mouseClick(w.model_button,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,w.model_button.icon_rect().center());app.processEvents()
    assert opened==[(True,True)] and not errors


def test_dynamic_text_and_progress_keep_controls_in_place(workbench):
    w,app,wait,errors=workbench;w.resize(1440,900);settle(app)
    w.task=object();w.task_kind='automatic';w.task_title='测试任务';w.progress_presentation.begin();w.update_controls();w.task_progress(1,10,'读取数据');settle(app)
    before=rectangles(w);task_slot=w.statusBar().text_slot.geometry()
    w.project_title.setText('a_very_long_project_name_'*20+'.gfm')
    w.model_runtime.setText('设备：CPU（回退） · '+'加载状态'*100)
    w.image_info.setText('90000 × 80000 · 12 波段\n影像投影：'+'投影说明'*100+'\n模型 RGB：1/2/3')
    w.prompt_counters.set_points([[0,0,1]]*12000+[[0,0,0]]*8000)
    w.edit_status.setText('当前编辑状态'*100);w.task_text.setText('正在准备影像'*100)
    try:
        w.update_controls();w.task_progress(1,10,'长路径/'*100);settle(app)
        assert w.progress.isVisible() and w.cancel_button.isVisible()
        assert rectangles(w)==before
        assert w.statusBar().text_slot.geometry()==task_slot
    finally:
        w.progress_presentation.finish('测试任务','cancelled');w.task=None;w.task_kind=None;w.update_controls();settle(app)
    assert rectangles(w)==before
    assert not errors


def test_each_mode_uses_compact_stable_height(workbench):
    w,app,wait,errors=workbench;w.resize(1440,900)
    im=fake_image('one');im['ready']=True;w.project['images']=[im];w.refresh_images();w.images.setCurrentRow(0)
    settle(app);before=rectangles(w)
    settle(app)
    assert w.mode_settings.currentWidget() is w.prompt_group
    assert not hasattr(w,'auto_group') and not hasattr(w,'tabs')
    w.draft={'geometry':mapping(box(100,100,200,200)),'points':[],'pending':False}
    w.refresh_labels();w.begin_reshape();settle(app)
    assert w.mode_settings.currentWidget() is w.reshape_group
    assert w.editor_group.isVisible() and not w.editor_group.isEnabled()
    assert 0<=w.mode_settings.height()-w.reshape_group.layout().minimumSize().height()<=16
    reshaping=rectangles(w)
    w.reshape_session['error']='重塑操作提示'*100;w.update_controls();settle(app)
    assert rectangles(w)==reshaping
    w.cancel_reshape();settle(app)
    assert w.mode_settings.currentWidget() is w.prompt_group and rectangles(w)==before
    assert not errors


def test_transient_notifications_do_not_hide_or_resize_status_items(workbench):
    w,app,wait,errors=workbench;w.resize(1024,700);settle(app)
    bar=w.statusBar();before=rectangles(w);slot=bar.text_slot.geometry()
    bar.showMessage('提示说明'*100,30);settle(app)
    assert bar.currentMessage()=='提示说明'*100
    assert bar.notice.toolTip()==bar.currentMessage() and w.state_label.isVisible()
    assert bar.text_slot.geometry()==slot and rectangles(w)==before
    QTest.qWait(50);settle(app)
    assert bar.currentMessage()=='' and bar.text_slot.currentIndex()==0
    assert bar.text_slot.geometry()==slot and rectangles(w)==before


def test_visible_panel_controls_fit_their_cards_and_captions(workbench):
    w,app,wait,errors=workbench;w.resize(1024,700);settle(app)
    for mode in (0,):
        settle(app)
        for scroll in (w.image_scroll,w.editor_scroll):
            root=scroll.widget()
            assert root.width()<=scroll.viewport().width()
            for control in root.findChildren(QPushButton)+root.findChildren(QToolButton)+root.findChildren(QComboBox):
                if control.isHidden() or not control.isVisibleTo(root):continue
                parent=control.parentWidget()
                assert parent.rect().contains(control.geometry()),(control,control.geometry(),parent.rect())
                if isinstance(control,(QPushButton,QToolButton)):
                    assert control.fontMetrics().horizontalAdvance(control.text())+10<=control.width(),control.text()
    project=w.project_title.parentWidget()
    assert w.project_title.y()==30 and project.rect().contains(w.recover_button.geometry())
    save=next(button for button in project.findChildren(QToolButton) if button.defaultAction() is w.project_actions['save'])
    assert save.y()==w.recover_button.y() and abs(save.width()-w.recover_button.width())<=1
    assert w.recover_button.x()>save.x()


def test_point_counter_digits_cannot_move_other_fields(workbench):
    w,app,wait,errors=workbench;settle(app)
    counter=w.prompt_counters
    before=[child.geometry() for child in counter.findChildren(QLabel)]
    counter.set_points([[0,0,1]]*15000+[[0,0,0]]*2);settle(app)
    assert [child.geometry() for child in counter.findChildren(QLabel)]==before
    assert [value.text() for value in counter.values]==['15000','2']


def test_label_columns_fill_available_width_and_show_scrollbar_only_for_overflow(workbench):
    from geoforma.ui.label_table import LabelRow
    from geoforma.ui.label_status import status_layout
    w,app,wait,errors=workbench;w.resize(1440,900);settle(app)
    w.label_presenter.sync([LabelRow('one','目标','未保存')]);settle(app)
    table=w.labels_table;geometry=table.geometry();column_widths=[table.columnWidth(i) for i in range(3)]
    assert not table.body_scrollbar.isVisible()
    assert sum(table.columnWidth(i) for i in range(3))==table.viewport().width()
    w.label_presenter.sync([LabelRow(str(i),'很长的类别名称'*20,'人工编辑') for i in range(100)]);settle(app)
    assert [table.columnWidth(i) for i in range(3)]==column_widths and table.geometry()==geometry
    assert sum(table.columnWidth(i) for i in range(3))==table.viewport().width()
    assert table.body_scrollbar.isVisible()
    badge,_=status_layout(table.visualItemRect(table.item(0,2)),table.fontMetrics(),'人工编辑')
    assert badge.right()<table.body_scrollbar.geometry().left()
    header=table.horizontalHeader()
    assert header.geometry().right()==table.viewport().geometry().right()
    assert table.body_scrollbar.mapTo(table,table.body_scrollbar.rect().topLeft()).y()>header.geometry().bottom()
    table.body_scrollbar.setValue(15);assert table.verticalScrollBar().value()==15
    table.verticalScrollBar().setValue(20);scroll=table.verticalScrollBar().value()
    w.label_presenter.sync([LabelRow(str(i),'类别','未保存') for i in range(100)]);settle(app)
    assert table.verticalScrollBar().value()==scroll and table.geometry()==geometry
    w.label_presenter.sync([]);settle(app)
    assert not table.body_scrollbar.isVisible()
    assert sum(table.columnWidth(i) for i in range(3))==table.viewport().width()
