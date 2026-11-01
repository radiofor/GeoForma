import os,time
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtCore import Qt,QPointF
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from shapely.geometry import box,mapping
from geoforma.window import MainWindow
from geoforma.theme import SELECTION, EDITING


def settled(w,app):
    deadline=time.monotonic()+4
    while time.monotonic()<deadline:
        app.processEvents()
        if w.candidate_task is None and w.candidate_key==w.candidate_signature():return
        QTest.qWait(5)
    pytest.fail('Candidate index did not finish')


@pytest.fixture
def scene():
    app=QApplication.instance() or QApplication([]);w=MainWindow(auto_prepare=False);w.autosave=lambda:None
    w.image={'id':'image','width':1000,'height':1000,'ready':True,'model_recipe':None}
    w.project['labels']=[dict(id=i,image_id='image',status='candidate',class_id=None,geometry=mapping(box(x,100,x+100,200)),window=[0,0,1000,1000]) for i,x in [('a',100),('b',300),('c',500)]]
    w.view.set_image(1000,1000);w.show();app.processEvents();w.refresh_labels();settled(w,app)
    yield w,app
    w.image=None;w.dirty=False;w.close();app.processEvents()


@pytest.mark.parametrize('tool',['pan','select','reshape'])
def test_list_click_highlights_without_zoom_and_double_click_locates(scene,tool):
    w,app=scene;w.set_tool(tool);table=w.labels_table;before=w.view.transform()
    point=table.visualItemRect(table.item(0,0)).center()
    QTest.mouseClick(table.viewport(),Qt.MouseButton.LeftButton,pos=point);app.processEvents()
    assert w.selected_ids=={'a'} and w.view.transform()==before
    assert w.view.overlay_records['a'].pen().color().name()==SELECTION and not w.draft
    QTest.mouseDClick(table.viewport(),Qt.MouseButton.LeftButton,pos=point);app.processEvents()
    assert w.view.transform().m11()>before.m11() and w.view.mode==tool
    assert w.mode_actions[tool].isChecked()


def test_delete_only_removes_target_and_preserves_view_and_other_items(scene):
    w,app=scene;w.select_items('labels',['a'])
    b=w.view.overlay_records['b'];c=w.view.overlay_records['c'];cell=w.labels_table.item(1,0)
    transform=w.view.transform();center=w.view.mapToScene(w.view.viewport().rect().center())
    w.delete_selected()
    assert w.view.overlay_records['b'] is b and w.view.overlay_records['c'] is c
    assert w.pending_review is None and not w.draft
    settled(w,app)
    assert w.view.overlay_records['b'] is b and w.labels_table.item(0,0) is cell
    assert w.view.transform()==transform and w.view.mapToScene(w.view.viewport().rect().center())==center
    assert not w.selected_ids and 'a' not in w.view.overlay_records


def test_map_click_works_in_select_and_pan_and_point_uses_same_highlight(scene):
    w,app=scene
    for mode,identifier,x in [('select','a',150),('pan','b',350)]:
        w.view.set_mode(mode);p=w.view.mapFromScene(QPointF(x,150))
        QTest.mouseClick(w.view.viewport(),Qt.MouseButton.LeftButton,pos=p);app.processEvents()
        assert w.selected_ids=={identifier}
        assert w.view.overlay_records[identifier].pen().color().name()==SELECTION and not w.draft
    w.view.prompts([[350,150,1]],selected={0});point=w.view.point_records[0]
    assert point.pen().color().name()==SELECTION
    w.view.prompts([[350,150,1]],selected={0});assert w.view.point_records[0] is point
