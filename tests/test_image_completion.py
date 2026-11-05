"""The manual image marker stays independent from preparation and annotation."""
import copy
import pytest
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from geoforma.raster_metadata import validate_metadata
from geoforma.raster_snapshot import image_snapshot
from geoforma.storage import load_project
from geoforma.ui.raster_presenter import REVIEW_COMPLETE_ROLE
from test_workbench import workbench,fake_image
from test_project_autosave import automatic_project,first_save,saved
from test_reshape import raster_image


def click_marker(w,app,row):
    item=w.images.item(row);w.images.scrollToItem(item);app.processEvents()
    rect=w.images.itemDelegate().review_rect(w.images.visualItemRect(item))
    QTest.mouseClick(w.images.viewport(),Qt.MouseButton.LeftButton,pos=rect.center());app.processEvents()


def test_marker_navigates_only_on_completion_and_preserves_image_drafts(workbench):
    w,app,wait,errors=workbench
    images=[fake_image(str(i),f'image{i}.tif') for i in range(3)]
    images[0]['ready']=True;w.project['images']=images;w.refresh_images();w.images.setCurrentRow(0)
    w.add_point(230,240,1);draft=copy.deepcopy(w.draft)
    labels=copy.deepcopy(w.project['labels']);snapshot=image_snapshot(images[0])
    click_marker(w,app,0)
    assert images[0]['review_complete'] is True and w.image is images[1]
    assert w.images.item(0).data(REVIEW_COMPLETE_ROLE) is True
    assert [im['ready'] for im in images]==[True,False,False] and w.project['labels']==labels
    assert image_snapshot(images[0])==snapshot
    w.images.setCurrentRow(0);assert w.draft==draft
    click_marker(w,app,0)
    assert images[0]['review_complete'] is False and w.image is images[0]
    click_marker(w,app,1)
    assert images[1]['review_complete'] is True and w.image is images[2]
    click_marker(w,app,1)
    assert images[1]['review_complete'] is False and w.image is images[2]
    click_marker(w,app,2)
    assert images[2]['review_complete'] is True and w.image is images[2]
    click_marker(w,app,2)
    assert images[2]['review_complete'] is False and w.image is images[2] and not errors


def test_clicking_name_or_readiness_does_not_toggle_marker(workbench):
    w,app,wait,errors=workbench;w.project['images']=[fake_image('a'),fake_image('b','b.tif')]
    w.refresh_images();w.images.setCurrentRow(0);app.processEvents()
    rect=w.images.visualItemRect(w.images.item(1))
    QTest.mouseClick(w.images.viewport(),Qt.MouseButton.LeftButton,pos=rect.center())
    assert w.image is w.project['images'][1] and not w.image.get('review_complete',False)
    QTest.mouseClick(w.images.viewport(),Qt.MouseButton.LeftButton,pos=rect.topRight()+QPoint(-17,rect.height()//2))
    assert not w.image.get('review_complete',False) and not errors


def test_marker_obeys_navigation_lock(workbench,monkeypatch):
    w,app,wait,errors=workbench;w.project['images']=[fake_image('a')];w.refresh_images();w.images.setCurrentRow(0)
    monkeypatch.setattr('geoforma.operation_state.can_browse',lambda _:False)
    click_marker(w,app,0)
    assert not w.image.get('review_complete',False)


def test_marker_is_autosaved_to_project(automatic_project,monkeypatch,raster_image):
    w,app,tmp=automatic_project;w.project['images']=[raster_image];w.refresh_images();w.images.setCurrentRow(0)
    path=first_save(w,tmp,monkeypatch)
    click_marker(w,app,0);saved(w,app)
    assert load_project(path)['images'][0]['review_complete'] is True
    click_marker(w,app,0);saved(w,app)
    assert load_project(path)['images'][0]['review_complete'] is False


def test_marker_metadata_rejects_nonboolean():
    image=fake_image('a');validate_metadata(image)
    for value in (None,0,1,'true',[]):
        with pytest.raises(ValueError,match='完成标记'):validate_metadata(dict(image,review_complete=value))
