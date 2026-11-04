import copy
import pytest
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QComboBox
from shapely.geometry import box,mapping,MultiPolygon
from test_reshape import workbench,raster_image


def second_class(w):
    w.project['classes'].append({'id':2,'name':'第二类'});w.refresh_classes();w.refresh_labels()


def test_four_buttons_have_the_requested_layout(workbench):
    w,app,_=workbench;w.show();app.processEvents()
    assert not hasattr(w,'edit_button') and not hasattr(w,'undo_label_button')
    p=[b.mapTo(w,b.rect().center()) for b in (w.previous_button,w.next_button,w.zoom_button,w.delete_button)]
    assert p[0].y()==p[1].y()<p[2].y()==p[3].y()
    assert p[0].x()<p[1].x() and p[2].x()<p[3].x()
    assert w.delete_action.shortcut().toString()=='Del'


def test_saved_row_class_changes_only_that_label_and_is_undoable(workbench):
    w,app,_=workbench;w.project['labels'].append(dict(w.project['labels'][0],id='other',geometry=mapping(box(60,60,70,70))))
    second_class(w);before=copy.deepcopy(w.project['labels']);combo=w.labels_table.category_combo(0)
    assert isinstance(combo,QComboBox) and combo.currentData()==1
    combo.setCurrentIndex(combo.findData(2))
    assert [l['class_id'] for l in w.project['labels']]==[2,1] and not w.draft
    w.undo_context();assert w.project['labels']==before
    assert w.labels_table.category_combo(0).currentData()==1
    w.redo_context();assert w.project['labels'][0]['class_id']==2


def test_each_unsaved_component_retains_its_own_class(workbench):
    w,app,_=workbench;second_class(w);w.project['labels']=[];w.single_polygon.setChecked(False)
    w.draft={'geometry':mapping(MultiPolygon([box(10,10,20,20),box(40,40,45,45)])),'points':[],'pending':False};w.refresh_labels()
    combo=w.labels_table.category_combo(1);combo.setCurrentIndex(combo.findData(2))
    assert not w.project['labels'] and all(r.status=='未保存' for r in w.label_presenter.rows)
    w.undo_context();assert w.labels_table.category_combo(1).currentData()==1
    w.redo_context();assert w.labels_table.category_combo(1).currentData()==2
    w.confirm();assert [l['class_id'] for l in w.project['labels']]==[1,2]


def test_del_and_delete_button_can_both_be_undone(workbench):
    w,app,_=workbench;w.show();app.processEvents();before=copy.deepcopy(w.project['labels'])
    w.labels_table.setFocus();QTest.keyClick(w.labels_table,Qt.Key.Key_Delete);app.processEvents()
    assert not w.project['labels']
    QTest.keyClick(w.labels_table,Qt.Key.Key_Z,Qt.KeyboardModifier.ControlModifier)
    assert w.project['labels']==before
    w.select_label('target');w.delete_button.click();assert not w.project['labels']
    w.undo_context();assert w.project['labels']==before


def test_delete_unsaved_component_and_restore_it(workbench):
    w,app,_=workbench;w.project['labels']=[];w.single_polygon.setChecked(False)
    w.draft={'geometry':mapping(MultiPolygon([box(10,10,20,20),box(40,40,45,45)])),'points':[],'pending':False};w.refresh_labels()
    ids=[r.identifier for r in w.label_presenter.rows];w.select_label(ids[1]);w.delete_button.click()
    assert [r.identifier for r in w.label_presenter.rows]==ids[:1] and not w.project['labels']
    w.undo_context();assert [r.identifier for r in w.label_presenter.rows]==ids
    w.select_label(ids[0]);w.delete_button.click();assert len(w.label_presenter.rows)==1
    w.select_label(ids[1]);w.delete_button.click();assert not w.draft and not w.label_presenter.rows
    w.undo_context();assert len(w.label_presenter.rows)==1


def test_navigation_only_selects_and_preserves_the_draft(workbench):
    w,app,_=workbench;w.draft={'geometry':mapping(box(60,60,70,70)),'points':[],'pending':False};w.refresh_labels()
    before=copy.deepcopy(w.draft);identifier=w.draft_labels()[0]['id']
    w.select_label('target');w.next_button.click()
    assert w.selected_id==identifier and w.draft==before
    w.previous_button.click();assert w.selected_id=='target' and w.draft==before


def test_category_fields_have_padding_and_align_with_the_row_center(workbench):
    w,app,tmp=workbench
    w.project['labels']=[dict(w.project['labels'][0],id=str(i),geometry=mapping(box(i*12,20,i*12+8,28))) for i in range(6)]
    w.resize(1280,1020);w.refresh_labels();w.show();app.processEvents()
    table=w.labels_table;previous_bottom=None
    for row in range(6):
        combo=table.category_combo(row);cell=table.visualItemRect(table.item(row,1))
        pos=combo.mapTo(table.viewport(),QPoint(0,0))
        assert pos.x()>=cell.left()+5 and pos.x()+combo.width()<=cell.right()-4
        assert pos.y()>=cell.top()+2 and pos.y()+combo.height()<=cell.bottom()-1
        assert cell.height()<=combo.height()+8
        assert abs(pos.y()+combo.height()/2-(cell.top()+cell.height()/2))<=1
        assert abs(table.visualItemRect(table.item(row,0)).center().y()-cell.center().y())<=1
        assert abs(table.visualItemRect(table.item(row,2)).center().y()-cell.center().y())<=1
        if previous_bottom is not None:assert 4<=pos.y()-previous_bottom<=8
        previous_bottom=pos.y()+combo.height()
    table.grab().save(str(tmp/'label_rows.png'))
    combo=table.category_combo(0);combo.showPopup();app.processEvents()
    assert abs(combo.view().window().width()-combo.width())<=1
    combo.hidePopup()


@pytest.mark.parametrize('width',[270,294,330])
def test_values_and_status_contents_align_with_their_headers(workbench,width):
    from PySide6.QtCore import QRectF
    from geoforma.ui.label_status import status_layout,STYLES
    w,app,tmp=workbench;w.show();w.resize(1280,1020);table=w.labels_table
    table.setFixedWidth(width);app.processEvents();header=table.horizontalHeader()
    assert table.columnWidth(1)>table.columnWidth(2)>table.columnWidth(0)
    def axis(column):
        origin=table.viewport().mapFromGlobal(header.viewport().mapToGlobal(QPoint(header.sectionViewportPosition(column),0)))
        return origin.x()+header.sectionSize(column)/2
    serial=QRectF(table.visualItemRect(table.item(0,0)))
    assert abs(serial.center().x()-axis(0))<=1
    combo=table.category_combo(0);caption=QRectF(combo.text_rect())
    text_x=combo.mapTo(table.viewport(),QPoint(0,0)).x()+caption.center().x()
    assert abs(text_x-axis(1))<=1
    for text in STYLES:
        badge,caption=status_layout(table.visualItemRect(table.item(0,2)),table.fontMetrics(),text)
        assert abs(badge.center().x()-axis(2))<=1
        assert abs(caption.center().x()-badge.center().x())<=1
        assert abs(caption.center().y()-badge.center().y())<=1
        assert table.fontMetrics().horizontalAdvance(text)<=caption.width()
    if width==294:table.grab().save(str(tmp/'header_aligned.png'))
