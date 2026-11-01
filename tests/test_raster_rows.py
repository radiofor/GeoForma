"""Preparation updates a single retained row without scroll or panel resets."""
import threading
from dataclasses import replace
from PySide6.QtCore import Qt,QRect,QPoint
from PySide6.QtGui import QImage,QPainter
from PySide6.QtWidgets import QApplication,QListWidget,QStyleOptionViewItem
from geoforma.theme import install_theme
from geoforma.ui.raster_presenter import RasterListPresenter,RasterRow,IDENTIFIER_ROLE
from geoforma.ui.raster_list import RasterItemDelegate
from test_workbench import workbench,fake_image
from test_background_activity import until


def test_new_rows_fade_while_existing_rows_and_readiness_updates_stay_stable():
    app=QApplication.instance() or QApplication([]);install_theme(app)
    view=QListWidget();view.resize(260,270);delegate=RasterItemDelegate(view);view.setItemDelegate(delegate)
    presenter=RasterListPresenter(view);rows=[RasterRow(str(i),'影像 '+str(i),False,'waiting') for i in range(5)]
    presenter.sync(rows[:2],'0');view.show();app.processEvents();old_item=view.item(0)
    def crop(image,rect):
        ratio=image.devicePixelRatio()
        return image.copy(QRect(round(rect.x()*ratio),round(rect.y()*ratio),round(rect.width()*ratio),round(rect.height()*ratio)))
    old_rect=view.visualItemRect(old_item);old_frame=crop(view.viewport().grab().toImage(),old_rect)
    presenter.sync(rows,'0',animate=True);animation=delegate.reveal_animation;animation.pause();app.processEvents()
    assert set(delegate.revealing)=={'2','3','4'} and view.item(0) is old_item
    rect=view.visualItemRect(view.item(2));geometry=view.geometry();frames=[];changes=[]
    view.model().dataChanged.connect(lambda *args:changes.append(True))
    for tick in (0,70,animation.duration()):
        animation.setCurrentTime(tick);app.processEvents()
        frame=view.viewport().grab().toImage();frames.append(crop(frame,rect))
        assert crop(frame,old_rect)==old_frame and view.geometry()==geometry
    assert frames[0]!=frames[1] and frames[1]!=frames[2] and not changes
    presenter.sync(rows+[RasterRow('next','下一幅',False,'waiting')],'0',animate=True)
    animation.pause();animation.setCurrentTime(60)
    rows[3]=replace(rows[3],ready=True);presenter.sync(rows+[RasterRow('next','下一幅',False,'waiting')],'0',animate=True)
    assert animation.currentTime()==60 and set(delegate.revealing)=={'next'}
    assert view.item(3).data(Qt.ItemDataRole.UserRole) and view.currentItem() is old_item
    animation.setCurrentTime(animation.duration());assert not delegate.revealing
    view.close()


def test_large_reveal_preserves_scroll_and_stops_when_hidden():
    app=QApplication.instance() or QApplication([]);view=QListWidget();view.resize(260,180)
    delegate=RasterItemDelegate(view);view.setItemDelegate(delegate);presenter=RasterListPresenter(view)
    rows=[RasterRow(str(i),'影像 '+str(i),False,'waiting') for i in range(1250)]
    presenter.sync(rows[:50],'0');view.show();app.processEvents();view.verticalScrollBar().setValue(200)
    scroll=view.verticalScrollBar().value();item=view.currentItem()
    presenter.sync(rows,'0',animate=True);animation=delegate.reveal_animation;animation.pause()
    assert animation.duration()<=240
    for tick in (0,80,160,animation.duration()):
        animation.setCurrentTime(tick);app.processEvents()
        assert view.verticalScrollBar().value()==scroll and view.currentItem() is item
    assert not delegate.revealing
    presenter.sync(rows+[RasterRow('next','下一幅',False,'waiting')],'0',animate=True)
    assert delegate.revealing
    view.hide();app.processEvents();assert not delegate.revealing
    view.close()


def test_raster_list_fills_spare_height_even_without_images(workbench):
    w,app,wait,errors=workbench;w.resize(1440,1400)
    def settle():
        for _ in range(8):app.processEvents()
        w.raster_list_sizer.settle()
        for _ in range(8):app.processEvents()
    settle();height=w.images.height();help_top=w.help_group.mapTo(w.image_scroll.widget(),QPoint()).y()
    assert height>300
    for count in (1,80,0):
        w.project['images']=[fake_image(str(i)) for i in range(count)];w.refresh_images();settle()
        assert w.images.height()==height
        root=w.image_scroll.widget()
        assert w.help_group.mapTo(root,QPoint()).y()==help_top
        bottom=w.help_group.mapTo(root,QPoint(0,w.help_group.height())).y()
        assert 0<=w.image_scroll.viewport().height()-bottom<=4
    w.resize(1440,900);settle()
    assert w.raster_list_sizer.minimum_height<=w.images.height()<height
    w.resize(1440,1400);settle();assert w.images.height()==height
    assert not errors


def test_sidebar_shrinks_list_for_wrapped_directory_before_showing_outer_scrollbar(workbench):
    w,app,wait,errors=workbench;w.resize(1440,1400)
    def settle():
        for _ in range(12):app.processEvents()
    settle();bar=w.image_scroll.verticalScrollBar();original=w.images.height()
    assert not bar.isVisible() and bar.maximum()==0
    w.project['images']=[fake_image(str(i)) for i in range(120)];w.refresh_images();w.images.setCurrentRow(0);settle()
    assert w.images.verticalScrollBar().maximum()>0 and not bar.isVisible()
    short=w.image_info.directory.text();height=w.images.height()
    w.image_info.directory.setText('F:/'+('/'.join(['long_directory_component']*7)));settle()
    assert w.images.height()<height and not bar.isVisible() and bar.maximum()==0
    viewport=w.image_scroll.viewport()
    bottom=w.help_group.mapTo(viewport,QPoint(0,w.help_group.height())).y()
    assert 0<=viewport.height()-bottom<=4
    w.image_info.directory.setText(short);settle();assert w.images.height()==height
    w.resize(1440,700);settle()
    assert w.images.height()==w.raster_list_sizer.minimum_height and bar.isVisible() and bar.maximum()>0
    bar.setValue(bar.maximum());settle()
    assert viewport.rect().contains(w.help_group.mapTo(viewport,w.help_group.rect().bottomRight()))
    w.resize(1440,1400);settle()
    assert w.images.height()==original and not bar.isVisible() and bar.maximum()==0 and not errors


def test_presenter_changes_only_one_row_and_retains_scroll_and_items():
    app=QApplication.instance() or QApplication([]);view=QListWidget();view.resize(220,150)
    presenter=RasterListPresenter(view);rows=[RasterRow(str(i),'影像 '+str(i),False,'waiting') for i in range(60)]
    presenter.sync(rows,'0');view.show();app.processEvents();view.verticalScrollBar().setValue(35)
    scroll=view.verticalScrollBar().value();items=[view.item(i) for i in range(60)];changes=[];structures=[]
    view.model().dataChanged.connect(lambda first,last,roles:changes.append((first.row(),last.row())))
    view.model().modelReset.connect(lambda:structures.append('reset'))
    view.model().rowsInserted.connect(lambda *args:structures.append('insert'))
    view.model().rowsRemoved.connect(lambda *args:structures.append('remove'))
    rows[22]=replace(rows[22],ready=True,detail='complete');presenter.sync(rows,'0');app.processEvents()
    assert changes and set(changes)=={(22,22)} and not structures
    assert view.verticalScrollBar().value()==scroll and view.currentItem() is items[0]
    assert all(view.item(i) is item for i,item in enumerate(items))
    changes.clear();presenter.sync(rows,'0');assert not changes
    rows.reverse();presenter.sync(rows,'0')
    assert view.currentItem().data(IDENTIFIER_ROLE)=='0' and view.item(0) is items[-1]
    view.close()


def test_completed_image_is_updated_individually_without_rebuilding_or_scrolling(workbench):
    w,app,wait,errors=workbench;w.project['images']=[fake_image(str(i),f'folder/{i}.tif') for i in range(40)]
    w.refresh_images();w.images.setCurrentRow(0);w.raster_list_sizer.settle();app.processEvents()
    w.images.verticalScrollBar().setValue(w.images.verticalScrollBar().maximum()//2)
    scroll=w.images.verticalScrollBar().value();items=[w.images.item(i) for i in range(40)];structural=[]
    for signal in (w.images.model().modelReset,w.images.model().rowsInserted,w.images.model().rowsRemoved):signal.connect(lambda *args:structural.append(True))
    for index in (20,21):
        release=threading.Event();started=threading.Event()
        def prepare(image,config,bounds,task):
            started.set()
            while not release.wait(.002):task.check()
            return dict(count=9,hits=0,device='cpu',checkpoint=config['checkpoint'])
        w.service.preprocess=prepare
        try:
            w.start_preparation(w.project['images'][index]);until(app,started.is_set)
            assert not items[index].data(Qt.ItemDataRole.UserRole)
            release.set();wait()
            assert items[index].data(Qt.ItemDataRole.UserRole) and not items[index+1].data(Qt.ItemDataRole.UserRole)
            assert all(w.images.item(i) is item for i,item in enumerate(items))
            assert not structural and w.images.verticalScrollBar().value()==scroll
            assert w.images.currentItem() is items[0]
        finally:release.set();wait()
    assert not errors


def test_readiness_marker_and_empty_placeholder_keep_the_same_right_slot():
    app=QApplication.instance() or QApplication([]);view=QListWidget();delegate=RasterItemDelegate(view)
    view.setItemDelegate(delegate);view.resize(140,100)
    presenter=RasterListPresenter(view);row=RasterRow('id','a_very_long_raster_filename_that_must_be_elided.tif',False,'')
    images=[]
    for ready in (False,True):
        presenter.sync([replace(row,ready=ready)])
        image=QImage(110,34,QImage.Format.Format_ARGB32);image.fill(Qt.GlobalColor.white)
        option=QStyleOptionViewItem();option.initFrom(view);option.rect=QRect(0,0,110,34)
        painter=QPainter(image);delegate.paint(painter,option,view.model().index(0,0));painter.end();images.append(image)
        assert view.item(0).text()==row.title
    teal=[(x,y) for y in range(34) for x in range(110) if images[1].pixelColor(x,y).name()=='#087f83']
    assert teal and min(x for x,y in teal)>=84
    assert any(images[0].pixelColor(x,y)!=Qt.GlobalColor.white for x in range(84,101) for y in range(8,26))
    assert images[0].copy(0,0,78,34)==images[1].copy(0,0,78,34)
    view.show();app.processEvents()
    assert not view.horizontalScrollBar().isVisible() and view.visualItemRect(view.item(0)).width()<=view.viewport().width()
    view.close()
