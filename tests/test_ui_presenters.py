import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication,QTableWidget
from geoforma.ui.label_table import LabelRow,LabelTablePresenter
from geoforma.ui.label_lookup import LabelLookup


def test_presenter_noop_emits_no_change_and_selection_reuses_cells():
    app=QApplication.instance() or QApplication([]);table=QTableWidget(0,2);presenter=LabelTablePresenter(table)
    rows=[LabelRow('a','A','Review'),LabelRow('b','B','Review')];presenter.sync(rows)
    a,b=table.item(0,0),table.item(1,0);events=[];table.itemChanged.connect(lambda *a:events.append(a))
    presenter.sync(rows);assert not events
    presenter.sync([rows[0],LabelRow('b','B','Review',selected=True)])
    assert table.item(0,0) is a and table.item(1,0) is b and b.isSelected()
    presenter.sync([LabelRow('b','B','Review',selected=True)])
    assert table.item(0,0) is b
    table.close()


def test_lookup_changes_with_save_delete_append_and_image_switch():
    lookup=LabelLookup();labels=[dict(id='a',image_id='one',status='candidate'),dict(id='other',image_id='two',status='confirmed')]
    assert [l['id'] for l in lookup.for_image(labels,'one')]==['a']
    assert lookup.for_id(labels,'one','a') is labels[0]
    labels.append(dict(id='saved',image_id='one',status='confirmed'))
    assert [l['id'] for l in lookup.for_image(labels,'one')]==['a','saved']
    labels=[l for l in labels if l['id']!='a']
    assert [l['id'] for l in lookup.for_image(labels,'one')]==['saved']
    assert lookup.for_id(labels,'one','a') is None
    assert [l['id'] for l in lookup.for_image(labels,'two')]==['other']


def test_switching_disjoint_images_reuses_table_items_with_new_ids():
    from geoforma.ui.label_table import LabelTable
    app=QApplication.instance() or QApplication([]);table=LabelTable();presenter=LabelTablePresenter(table)
    presenter.sync([LabelRow('old1','A','已保存',class_id=1),LabelRow('old2','A','已保存',class_id=1)])
    items=[table.item(i,1) for i in range(2)]
    presenter.sync([LabelRow('new1','B','已保存',class_id=2),LabelRow('new2','A','已保存',class_id=1)])
    assert [table.item(i,1) for i in range(2)]==items
    assert table.item(0,0).data(256)=='new1'
    assert table.item(0,1).text()=='B' and table.cellWidget(0,1) is None
    table.close()


def test_large_list_never_creates_per_row_editors():
    from geoforma.ui.label_table import LabelTable
    app=QApplication.instance() or QApplication([]);table=LabelTable();table.resize(300,240);table.show();app.processEvents()
    presenter=LabelTablePresenter(table)
    rows=[LabelRow(str(i),'A','已保存',class_id=1) for i in range(300)]
    presenter.sync(rows);app.processEvents()
    assert table.rowCount()==300 and all(table.cellWidget(i,1) is None for i in range(300))
    table.verticalScrollBar().setValue(table.verticalScrollBar().maximum());app.processEvents()
    assert table.item(299,1).text()=='A'
    presenter.sync([]);assert table.rowCount()==0
    table.close()
