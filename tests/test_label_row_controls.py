import copy
import pytest
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from shapely.geometry import box,mapping,MultiPolygon
from test_reshape import workbench,raster_image


def second_class(w):
    w.project['classes'].append({'id':2,'name':'第二类'});w.refresh_classes();w.refresh_labels()


def click_category(w,app,identifier):
    w.show();app.processEvents();buttons=w.category_buttons;item=buttons.items[identifier];buttons.scrollToItem(item);app.processEvents()
    QTest.mouseClick(buttons.viewport(),Qt.MouseButton.LeftButton,pos=buttons.visualItemRect(item).center());app.processEvents()


def test_removed_navigation_buttons_and_delete_shortcut(workbench):
    w,app,_=workbench;w.show();app.processEvents()
    assert all(not hasattr(w,name) for name in ('previous_button','next_button','zoom_button','delete_button'))
    assert w.delete_action.shortcut().toString()=='Del'


def test_saved_row_class_changes_only_that_label_and_is_undoable(workbench):
    w,app,_=workbench;w.project['labels'].append(dict(w.project['labels'][0],id='other',geometry=mapping(box(60,60,70,70))))
    second_class(w);before=copy.deepcopy(w.project['labels']);w.select_label('target')
    assert w.category_buttons.active==1
    click_category(w,app,2)
    assert [l['class_id'] for l in w.project['labels']]==[2,1] and w.selected_ids=={'target'} and not w.draft
    QTest.keyClick(w.category_buttons,Qt.Key.Key_Z,Qt.KeyboardModifier.ControlModifier);app.processEvents()
    assert w.project['labels']==before
    assert w.category_buttons.active==1
    QTest.keyClick(w.category_buttons,Qt.Key.Key_Z,Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.ShiftModifier);app.processEvents()
    assert w.project['labels'][0]['class_id']==2 and w.category_buttons.active==2


def test_each_unsaved_component_retains_its_own_class(workbench):
    w,app,_=workbench;second_class(w);w.project['labels']=[];w.single_polygon.setChecked(False)
    w.draft={'geometry':mapping(MultiPolygon([box(10,10,20,20),box(40,40,45,45)])),'points':[],'pending':False};w.refresh_labels()
    identifier=w.label_presenter.rows[1].identifier;w.select_label(identifier);click_category(w,app,2)
    assert not w.project['labels'] and all(r.status=='未保存' for r in w.label_presenter.rows)
    w.undo_context();assert w.label_presenter.rows[1].class_id==1
    w.redo_context();assert w.label_presenter.rows[1].class_id==2
    w.confirm();assert [l['class_id'] for l in w.project['labels']]==[1,2]


def test_del_can_be_undone(workbench):
    w,app,_=workbench;w.show();app.processEvents();before=copy.deepcopy(w.project['labels'])
    w.labels_table.setFocus();QTest.keyClick(w.labels_table,Qt.Key.Key_Delete);app.processEvents()
    assert not w.project['labels']
    QTest.keyClick(w.labels_table,Qt.Key.Key_Z,Qt.KeyboardModifier.ControlModifier)
    assert w.project['labels']==before
    w.select_label('target');QTest.keyClick(w.labels_table,Qt.Key.Key_Delete);assert not w.project['labels']
    w.undo_context();assert w.project['labels']==before


def test_del_from_category_buttons_deletes_selected_label_not_selected_point(workbench):
    w,app,_=workbench;w.show();app.processEvents();w.select_label('target')
    w.draft={'points':[[10,10,1]],'pending':True};w.selected_points={0};w.refresh_labels()
    w.category_buttons.setFocus();QTest.keyClick(w.category_buttons,Qt.Key.Key_Delete);app.processEvents()
    assert not w.project['labels'] and w.draft.get('points')==[[10,10,1]]
    w.undo_context();assert w.project['labels'][0]['id']=='target'


def test_delete_unsaved_component_and_restore_it(workbench):
    w,app,_=workbench;w.project['labels']=[];w.single_polygon.setChecked(False)
    w.draft={'geometry':mapping(MultiPolygon([box(10,10,20,20),box(40,40,45,45)])),'points':[],'pending':False};w.refresh_labels()
    ids=[r.identifier for r in w.label_presenter.rows];w.select_label(ids[1]);w.delete_selected()
    assert [r.identifier for r in w.label_presenter.rows]==ids[:1] and not w.project['labels']
    w.undo_context();assert [r.identifier for r in w.label_presenter.rows]==ids
    w.select_label(ids[0]);w.delete_selected();assert len(w.label_presenter.rows)==1
    w.select_label(ids[1]);w.delete_selected();assert not w.draft and not w.label_presenter.rows
    w.undo_context();assert len(w.label_presenter.rows)==1


def test_selection_only_highlights_and_preserves_the_draft(workbench):
    w,app,_=workbench;w.draft={'geometry':mapping(box(60,60,70,70)),'points':[],'pending':False};w.refresh_labels()
    before=copy.deepcopy(w.draft);identifier=w.draft_labels()[0]['id']
    w.select_label(identifier)
    assert w.selected_id==identifier and w.draft==before
    w.select_label('target');assert w.selected_id=='target' and w.draft==before


def test_category_buttons_require_one_selection_and_do_not_add_noop_history(workbench):
    w,app,_=workbench;second_class(w);w.show();app.processEvents()
    w.selected_ids.clear();w.selected_id=None;w.refresh_labels()
    assert not w.category_buttons.isEnabled() and w.category_buttons.active is None
    w.select_label('target');assert w.category_buttons.isEnabled() and w.category_buttons.active==1
    before=len(w.label_undo);click_category(w,app,1)
    assert len(w.label_undo)==before and w.category_buttons.active==1
    w.project['labels'].append(dict(w.project['labels'][0],id='other',geometry=mapping(box(60,60,70,70))))
    w.refresh_labels();w.select_items('labels',['target','other'])
    assert not w.category_buttons.isEnabled() and w.category_buttons.active is None


def test_category_management_updates_buttons_in_place_after_confirmation(workbench,monkeypatch):
    from geoforma.ui import modal
    w,app,_=workbench;w.select_label('target');w.show();app.processEvents()
    first=w.category_buttons.items[1];height=w.category_buttons.height()
    monkeypatch.setattr(modal,'dialog_result',lambda dialog,reader:(True,([{'id':1,'name':'湖泊','color':'#336699'},{'id':2,'name':'道路'}],3,1)))
    w.manage_classes();app.processEvents()
    assert w.category_buttons.items[1] is first and first.text()=='湖泊' and first.data(Qt.ItemDataRole.UserRole+2)=='#336699'
    assert set(w.category_buttons.items)=={1,2} and w.category_buttons.active==1 and w.category_buttons.height()==height
    monkeypatch.setattr(modal,'dialog_result',lambda dialog,reader:(True,([{'id':1,'name':'湖泊','color':'#336699'}],3,1)))
    w.manage_classes();app.processEvents()
    assert set(w.category_buttons.items)=={1} and w.category_buttons.items[1] is first and w.category_buttons.height()==height


def test_many_category_buttons_wrap_and_scroll_with_complete_names(workbench):
    w,app,_=workbench;name='较长类别名称_'*30
    w.project['classes']=[{'id':i,'name':name+str(i)} for i in range(1,13)]
    w.refresh_classes();w.refresh_labels();w.show();app.processEvents()
    buttons=w.category_buttons
    assert len(buttons.items)==12 and buttons.height()<=3*buttons.row_height
    assert buttons.items[12].toolTip()==name+'12'
    assert buttons.verticalScrollBar().maximum()>0
    w.select_label('target');click_category(w,app,12)
    assert w.project['labels'][0]['class_id']==12 and buttons.active==12


def test_long_category_name_uses_status_bar_without_overwriting_other_messages(workbench):
    w,app,_=workbench;name='长类别名称'*30
    w.project['classes']=[{'id':1,'name':name}];w.refresh_classes();w.refresh_labels();w.show();app.processEvents()
    w.statusBar().clearMessage();buttons=w.category_buttons
    QTest.mouseMove(buttons.viewport(),buttons.visualItemRect(buttons.items[1]).center());app.processEvents()
    assert w.statusBar().currentMessage()==name
    w.show_category_name('');assert not w.statusBar().currentMessage()
    w.statusBar().showMessage('已有任务状态');w.show_category_name(name)
    assert w.statusBar().currentMessage()=='已有任务状态'


def test_category_buttons_use_two_columns_without_unnecessary_scroll(workbench):
    w,app,_=workbench;w.project['classes']=[{'id':i,'name':'类别 '+str(i)} for i in range(1,5)]
    w.refresh_classes();w.refresh_labels();w.show()
    for _ in range(5):app.processEvents()
    buttons=w.category_buttons;rects=[buttons.visualItemRect(buttons.items[i]) for i in range(1,5)]
    assert rects[0].y()==rects[1].y()<rects[2].y()==rects[3].y()
    assert rects[0].right()<rects[1].left() and rects[2].right()<rects[3].left()
    assert buttons.verticalScrollBar().maximum()==0


def test_category_values_align_with_the_row_center(workbench):
    w,app,tmp=workbench
    w.project['labels']=[dict(w.project['labels'][0],id=str(i),geometry=mapping(box(i*12,20,i*12+8,28))) for i in range(6)]
    w.resize(1280,1020);w.refresh_labels();w.show();app.processEvents()
    table=w.labels_table
    for row in range(6):
        cell=table.visualItemRect(table.item(row,1))
        assert table.item(row,1).textAlignment()==Qt.AlignmentFlag.AlignCenter
        assert abs(table.visualItemRect(table.item(row,0)).center().y()-cell.center().y())<=1
        assert abs(table.visualItemRect(table.item(row,2)).center().y()-cell.center().y())<=1
    table.grab().save(str(tmp/'label_rows.png'))


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
    category=QRectF(table.visualItemRect(table.item(0,1)))
    assert abs(category.center().x()-axis(1))<=1
    for text in STYLES:
        badge,caption=status_layout(table.visualItemRect(table.item(0,2)),table.fontMetrics(),text)
        assert abs(badge.center().x()-axis(2))<=1
        assert abs(caption.center().x()-badge.center().x())<=1
        assert abs(caption.center().y()-badge.center().y())<=1
        assert table.fontMetrics().horizontalAdvance(text)<=caption.width()
    if width==294:table.grab().save(str(tmp/'header_aligned.png'))
