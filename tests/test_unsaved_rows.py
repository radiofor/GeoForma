import copy
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from shapely.geometry import box,mapping,MultiPolygon
from geoforma.theme import SELECTION
from test_reshape import workbench,raster_image


@pytest.mark.parametrize('multi',[False,True])
def test_unsaved_rows_and_canvas_share_ids_until_saved(workbench,multi):
    w,app,_=workbench;w.smooth_enabled.setChecked(False);w.single_polygon.setChecked(False)
    w.project['labels']=[];w.selected_ids.clear();w.selected_id=None
    geometry=mapping(MultiPolygon([box(10,10,20,20),box(40,40,45,45)])) if multi else mapping(box(10,10,20,20))
    w.draft={'geometry':geometry,'points':[],'pending':False};w.refresh_labels()
    rows=w.label_presenter.rows;count=2 if multi else 1
    assert len(rows)==count and all(r.status=='未保存' for r in rows)
    ids={r.identifier for r in rows}
    assert {i.data(0) for i in w.view.overlay_items}==ids
    cells={w.labels_table.item(i,0).data(Qt.ItemDataRole.UserRole):w.labels_table.item(i,0) for i in range(count)}
    w.show();app.processEvents()
    for row in range(count):
        QTest.mouseClick(w.labels_table.viewport(),Qt.MouseButton.LeftButton,pos=w.labels_table.visualItemRect(w.labels_table.item(row,0)).center())
        identifier=w.labels_table.item(row,0).data(Qt.ItemDataRole.UserRole)
        assert w.selected_id==identifier
        assert next(i for i in w.view.overlay_items if i.data(0)==identifier).pen().color().name()==SELECTION
    w.view.setFocus();QTest.keyClick(w.view.viewport(),Qt.Key.Key_Return)
    assert not w.draft and {l['id'] for l in w.project['labels']}==ids
    assert len(w.label_presenter.rows)==count and all(r.status=='已保存' for r in w.label_presenter.rows)
    assert all(w.labels_table.item(i,0) is cells[w.labels_table.item(i,0).data(Qt.ItemDataRole.UserRole)] for i in range(count))


def test_draft_class_geometry_and_cancel_stay_in_sync(workbench):
    w,app,_=workbench;w.smooth_enabled.setChecked(False)
    w.project['classes'].append({'id':2,'name':'新类别'});w.refresh_classes()
    w.draft={'geometry':mapping(box(40,40,50,50)),'points':[],'pending':False};w.refresh_labels()
    identifier=w.draft_labels()[0]['id'];w.classes.setCurrentIndex(w.classes.findData(2))
    row=next(r for r in w.label_presenter.rows if r.identifier==identifier)
    assert row.title=='新类别' and row.status=='未保存'
    w.draft['geometry']=mapping(box(60,60,70,70));w.refresh_labels()
    assert w.view.overlay_records['__draft'].path().boundingRect().left()==60
    assert w.draft_labels()[0]['id']==identifier
    w.clear_draft()
    assert identifier not in {r.identifier for r in w.label_presenter.rows}
    assert '__draft' not in w.view.overlay_records


def test_existing_edit_reuses_row_and_cancel_restores_saved_status(workbench):
    w,app,_=workbench;before=copy.deepcopy(w.project['labels']);cell=w.labels_table.item(0,0)
    w.edit_selected(locate=False)
    assert len(w.label_presenter.rows)==1 and w.label_presenter.rows[0].status=='未保存'
    assert w.labels_table.item(0,0) is cell
    w.clear_draft()
    assert w.project['labels']==before and w.label_presenter.rows[0].status=='已保存'


def test_empty_prediction_removes_the_previous_unsaved_row(workbench,monkeypatch):
    w,app,_=workbench;w.draft={'geometry':mapping(box(40,40,50,50)),'points':[],'pending':False};w.refresh_labels()
    identifier=w.draft_labels()[0]['id'];monkeypatch.setattr(w,'record_runtime',lambda result:None)
    w.predicted({'choices':[],'window':[0,0,100,100],'key':'test','cache_hit':True,'device':'cpu'})
    assert identifier not in {r.identifier for r in w.label_presenter.rows}
    assert '__draft' not in w.view.overlay_records
