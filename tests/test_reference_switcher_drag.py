"""Reference order and navigation remain stable across viewport sizes."""
import pytest
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from geoforma.reference_catalog import reorder_reference_groups
from test_workbench import workbench,fake_image
from test_project_autosave import automatic_project,first_save,saved
from test_reference_images import raster
from geoforma.storage import load_project


def drag_to(button,target,app):
    start=button.rect().center();destination=target.mapToGlobal(target.rect().center())
    QTest.mousePress(button,Qt.MouseButton.LeftButton,pos=start)
    QTest.mouseMove(button,button.mapFromGlobal(destination),20);app.processEvents()
    QTest.mouseRelease(button,Qt.MouseButton.LeftButton,pos=button.mapFromGlobal(destination));app.processEvents()


def test_group_reorder_keeps_other_images_and_unseen_groups():
    records=[dict(group='A',path='a/tile.tif'),dict(group='hidden',path='h/other.tif'),
             dict(group='B',path='b/tile.tif'),dict(group='A',path='a/other.tif'),dict(group='C',path='c/tile.tif')]
    result=reorder_reference_groups(records,['c','a','b'])
    assert [(r['group'],r['path']) for r in result]==[("C",'c/tile.tif'),('hidden','h/other.tif'),
        ('A','a/tile.tif'),('A','a/other.tif'),('B','b/tile.tif')]
    assert reorder_reference_groups(records,['a','b','c']) is records
    assert reorder_reference_groups(records,['a','a']) is records


@pytest.mark.parametrize(('start','target'),[(0,4),(4,0),(2,0),(2,4),(3,1),(1,3)])
def test_drag_in_both_directions_reaches_each_destination(workbench,start,target):
    w,app,wait,errors=workbench;image=fake_image('main','tile.tif');w.project['images']=[image]
    names=['A','B','C','D','E'];records=[dict(image,path=f'{name}/tile.tif',group=name,fingerprint=name) for name in names]
    w.project['references']=records;w.refresh_images();w.images.setCurrentRow(0);w.resize(2400,900);w.sync_reference_buttons()
    QTest.qWait(100);app.processEvents()
    source=w.reference_buttons[(names[start].casefold(),records[start]['path'])]
    destination=w.reference_buttons[(names[target].casefold(),records[target]['path'])]
    drag_to(source,destination,app);expected=names[:];expected.insert(target,expected.pop(start))
    assert [record['group'] for record in w.project['references']]==expected and not errors


def test_drag_reorders_without_selecting_or_reloading(workbench):
    w,app,wait,errors=workbench;image=fake_image('main','tile.tif');w.project['images']=[image]
    records=[dict(image,path=f'{name}/tile.tif',group=name,fingerprint=name) for name in ('NDWI','VV','VH','ESI')]
    w.project['references']=records;w.refresh_images();w.images.setCurrentRow(0);w.resize(2500,900);w.sync_reference_buttons()
    QTest.qWait(100);app.processEvents();w.display_reference=records[1];w.visible_reference=records[1];w.sync_reference_buttons()
    source=w.reference_buttons[('ndwi',records[0]['path'])];target=w.reference_buttons[('vh',records[2]['path'])]
    generation=w.render_generation;revision=w.dirty_revision
    drag_to(source,target,app)
    assert [record['group'] for record in w.project['references']]==['VV','VH','NDWI','ESI']
    assert w.display_reference is records[1] and w.render_generation==generation and w.dirty_revision>revision
    assert w.reference_buttons[('ndwi',records[0]['path'])] is source and not errors
    drag_to(w.reference_buttons[('esi',records[3]['path'])],w.reference_buttons[('vv',records[1]['path'])],app)
    assert [record['group'] for record in w.project['references']]==['ESI','VV','VH','NDWI']
    assert w.display_reference is records[1] and w.render_generation==generation and not errors
    QTest.mouseClick(source,Qt.MouseButton.LeftButton,pos=source.rect().center());app.processEvents()
    assert w.display_reference is records[0]


def test_dropping_outside_reference_row_cancels_reorder(workbench):
    w,app,wait,errors=workbench;image=fake_image('main','tile.tif');w.project['images']=[image]
    records=[dict(image,path=f'{name}/tile.tif',group=name,fingerprint=name) for name in ('A','B','C')]
    w.project['references']=records;w.refresh_images();w.images.setCurrentRow(0);w.resize(2200,900);w.sync_reference_buttons()
    QTest.qWait(100);app.processEvents();source=w.reference_buttons[('a',records[0]['path'])]
    outside=w.reference_switch_holder.viewport().mapToGlobal(QPoint(260,80));revision=w.dirty_revision
    QTest.mousePress(source,Qt.MouseButton.LeftButton,pos=source.rect().center())
    QTest.mouseMove(source,source.mapFromGlobal(outside),20);app.processEvents()
    QTest.mouseRelease(source,Qt.MouseButton.LeftButton,pos=source.mapFromGlobal(outside));app.processEvents()
    assert w.project['references']==records and w.dirty_revision==revision and not errors


def test_reference_removal_cancels_active_drag(workbench):
    w,app,wait,errors=workbench;image=fake_image('main','tile.tif');w.project['images']=[image]
    records=[dict(image,path=f'{name}/tile.tif',group=name,fingerprint=name) for name in ('A','B','C')]
    w.project['references']=records;w.refresh_images();w.images.setCurrentRow(0);w.resize(2200,900);w.sync_reference_buttons()
    QTest.qWait(100);app.processEvents();holder=w.reference_switch_holder;source=w.reference_buttons[('a',records[0]['path'])]
    target=w.reference_buttons[('c',records[2]['path'])].mapToGlobal(QPoint(47,15))
    QTest.mousePress(source,Qt.MouseButton.LeftButton,pos=source.rect().center())
    QTest.mouseMove(source,source.mapFromGlobal(target),20);app.processEvents()
    assert holder.drag is not None
    w.project['references']=records[1:];w.sync_reference_buttons();app.processEvents()
    assert holder.drag is None and not holder.drag_timer.isActive()
    assert [r['group'] for r in w.project['references']]==['B','C'] and not errors


def test_displaced_reference_buttons_animate_during_drag(workbench):
    w,app,wait,errors=workbench;image=fake_image('main','tile.tif');w.project['images']=[image]
    records=[dict(image,path=f'{name}/tile.tif',group=name,fingerprint=name) for name in ('A','B','C')]
    w.project['references']=records;w.refresh_images();w.images.setCurrentRow(0);w.resize(2200,900);w.sync_reference_buttons()
    QTest.qWait(100);app.processEvents();holder=w.reference_switch_holder;source=w.reference_buttons[('a',records[0]['path'])]
    destination=w.reference_buttons[('c',records[2]['path'])].mapToGlobal(QPoint(47,15))
    QTest.mousePress(source,Qt.MouseButton.LeftButton,pos=source.rect().center())
    QTest.mouseMove(source,source.mapFromGlobal(destination),1);app.processEvents()
    assert holder.shift_animations
    moving=next(iter(holder.shift_animations));before=moving.pos()
    QTest.qWait(55);app.processEvents();assert moving.pos()!=before
    QTest.mouseRelease(source,Qt.MouseButton.LeftButton,pos=source.mapFromGlobal(destination));app.processEvents()
    assert [r['group'] for r in w.project['references']]==['B','C','A'] and not errors


def test_navigation_uses_available_width_and_never_shows_scrollbar(workbench):
    w,app,wait,errors=workbench;image=fake_image('main','tile.tif');w.project['images']=[image]
    records=[dict(image,path=f'{name}/tile.tif',group=name,fingerprint=name) for name in ('A','B','C','D','E','F','G','H')]
    w.project['references']=records;w.refresh_images();w.images.setCurrentRow(0);w.sync_reference_buttons()
    holder=w.reference_switch_holder
    w.resize(2600,900);QTest.qWait(100);app.processEvents()
    assert holder.width()==holder.natural+2*holder.arrow_width+2*holder.layout().spacing()
    assert holder.left.isVisible() and holder.right.isVisible()
    assert not holder.left.isEnabled() and not holder.right.isEnabled()
    assert not holder.scroll.horizontalScrollBar().isVisible()
    w.resize(1440,900);QTest.qWait(100);app.processEvents()
    bar=holder.scroll.horizontalScrollBar()
    assert holder.width()<holder.natural and holder.left.isVisible() and holder.right.isVisible()
    assert not bar.isVisible() and bar.maximum()>0 and not holder.left.isEnabled() and holder.right.isEnabled()
    assert (holder.viewport().width()+holder.row.spacing())%(holder.button_width+holder.row.spacing())==0
    assert w.image_toolbar.width()>=w.image_toolbar.sizeHint().width()
    assert w.source_controls.parentWidget().rect().contains(w.source_controls.geometry())
    holder.right.click();QTest.qWait(190);app.processEvents()
    assert bar.value()>0 and holder.left.isEnabled()
    holder.left.click();QTest.qWait(190);app.processEvents();assert bar.value()==0 and not errors


def test_drag_at_viewport_edge_scrolls_and_reorders(workbench):
    w,app,wait,errors=workbench;image=fake_image('main','tile.tif');w.project['images']=[image]
    records=[dict(image,path=f'{name}/tile.tif',group=name,fingerprint=name) for name in ('A','B','C','D','E','F')]
    w.project['references']=records;w.refresh_images();w.images.setCurrentRow(0);w.resize(1440,900);w.sync_reference_buttons()
    QTest.qWait(100);app.processEvents();holder=w.reference_switch_holder;bar=holder.scroll.horizontalScrollBar()
    button=w.reference_buttons[('a',records[0]['path'])]
    edge=holder.viewport().mapToGlobal(QPoint(holder.viewport().width()-2,15))
    QTest.mousePress(button,Qt.MouseButton.LeftButton,pos=button.rect().center())
    QTest.mouseMove(button,button.mapFromGlobal(edge),20);QTest.qWait(400);app.processEvents()
    assert bar.value()>0
    QTest.mouseRelease(button,Qt.MouseButton.LeftButton,pos=button.mapFromGlobal(edge));app.processEvents()
    assert [r['group'] for r in w.project['references']].index('A')>=2 and not errors


def test_drag_order_autosaves_and_is_shared_across_images(automatic_project,monkeypatch):
    w,app,tmp=automatic_project;base=raster(tmp/'main'/'tile.tif');other=raster(tmp/'main'/'other.tif')
    refs=[dict(raster(tmp/name/file),group=name) for name,file in
          (('A','tile.tif'),('A','other.tif'),('B','tile.tif'),('C','tile.tif'),('C','other.tif'))]
    w.project['images']=[base,other];w.project['references']=refs;w.refresh_images();w.images.setCurrentRow(0)
    w.resize(2200,900);w.sync_reference_buttons();QTest.qWait(100);app.processEvents()
    path=first_save(w,tmp,monkeypatch)
    drag_to(w.reference_buttons[('a',refs[0]['path'])],w.reference_buttons[('c',refs[3]['path'])],app)
    saved(w,app)
    assert [r['group'] for r in load_project(path)['references']]==['B','C','C','A','A']
    w.images.setCurrentRow(1);app.processEvents()
    assert [w.reference_switches.layout().itemAt(i).widget().text() for i in range(2)]==['C','A']
