import copy
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from geoforma.theme import EDITING,SELECTION
from geoforma.rendering.label_item import LABEL_RED
from geoforma.ui.label_table import LabelRow
from test_reshape import workbench,raster_image
from shapely.geometry import box,mapping


def click_serial(w,app,row=0):
    QTest.mouseClick(w.labels_table.viewport(),Qt.MouseButton.LeftButton,
                    pos=w.labels_table.visualItemRect(w.labels_table.item(row,0)).center())
    app.processEvents()


def test_serial_columns_are_centered_numbered_and_incrementally_renumbered(workbench):
    w,app,_=workbench;table=w.labels_table
    w.label_presenter.sync([LabelRow('a','湖泊','已保存'),LabelRow('b','湖泊','已保存')])
    assert table.columnCount()==3 and table.horizontalHeaderItem(0).text()=='序号'
    assert [table.item(0,c).text() for c in range(3)]==['1','湖泊','已保存']
    cells=[table.item(1,c) for c in range(3)]
    w.label_presenter.sync([LabelRow('b','湖泊','已保存')])
    for c,item in enumerate(cells):
        assert table.item(0,c) is item and item.textAlignment()==Qt.AlignmentFlag.AlignCenter
    assert table.item(0,0).text()=='1'


def test_editing_does_not_select_but_serial_click_explicitly_selects(workbench):
    w,app,_=workbench;w.show();app.processEvents();w.edit_selected(locate=False)
    assert not w.selected_ids and not w.labels_table.selectedItems()
    item=w.view.overlay_records['__draft'];assert item.pen().color().name()==EDITING
    draft=copy.deepcopy(w.draft);click_serial(w,app)
    assert w.selected_ids=={'target'} and w.draft==draft
    assert w.view.overlay_records['__draft'] is item and item.pen().color().name()==SELECTION
    w.labels_table.clearSelection();app.processEvents()
    assert item.pen().color().name()==EDITING
    assert all(i.brush().color().alpha()==0 for i in w.view.overlay_records.values())


def test_reshape_target_is_independent_from_table_selection(workbench):
    w,app,_=workbench;w.show();app.processEvents();w.begin_reshape()
    session=w.reshape_session;assert not w.selected_ids and not w.labels_table.selectedItems()
    item=w.view.overlay_records['target'];assert item.pen().color().name()==EDITING
    click_serial(w,app)
    assert w.reshape_session is session and w.selected_ids=={'target'}
    assert item.pen().color().name()==SELECTION and item.brush().color().alpha()==0
    w.labels_table.clearSelection();app.processEvents()
    assert w.reshape_current(session)['id']=='target' and item.pen().color().name()==EDITING
    w.cancel_reshape();assert item.pen().color().name()==LABEL_RED


def test_selecting_another_row_does_not_replace_reshape_target(workbench):
    w,app,_=workbench
    w.project['labels'].append(dict(w.project['labels'][0],id='other',geometry=mapping(box(60,60,70,70))))
    w.refresh_labels();w.show();app.processEvents();w.begin_reshape()
    session=w.reshape_session;click_serial(w,app,1)
    assert w.selected_ids=={'other'} and w.reshape_current(session)['id']=='target'
    assert w.view.overlay_records['target'].pen().color().name()==EDITING
    assert w.view.overlay_records['other'].pen().color().name()==SELECTION


def test_all_outline_states_paint_transparent_interiors(workbench):
    from PySide6.QtGui import QImage,QPainter,QPen,QColor,QPainterPath
    from PySide6.QtWidgets import QStyleOptionGraphicsItem
    from geoforma.rendering.label_item import LabelItem
    path=QPainterPath();path.addRect(10,10,50,50)
    for color in (LABEL_RED,SELECTION,EDITING):
        image=QImage(80,80,QImage.Format.Format_ARGB32);image.fill(Qt.GlobalColor.transparent)
        item=LabelItem();item.setPath(path);item.setPen(QPen(QColor(color)));item.setBrush(QColor('red'))
        painter=QPainter(image);item.paint(painter,QStyleOptionGraphicsItem());painter.end()
        assert image.pixelColor(35,35).alpha()==0
        assert any(image.pixelColor(x,10).name()==color for x in range(12,58))
