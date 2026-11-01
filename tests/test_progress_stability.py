"""Fast imports and cached preparation retain every count and stable panels."""
from PySide6.QtCore import QObject,QEvent,Qt
from test_background_activity import until
from test_workbench import workbench,fake_image
from test_panel_flicker import PanelEvents
from test_stable_panels import settle


def test_fast_import_presents_every_file_in_order_before_committing(workbench,monkeypatch):
    from geoforma.controllers import images
    w,app,wait,errors=workbench
    monkeypatch.setattr(images,'inspect_source',lambda path:fake_image(path,path))
    monkeypatch.setattr(images,'make_recipe',lambda *args:{'bands':[1,2,3]})
    counts=[];committed=[]
    w.progress.model.changed.connect(lambda state:counts.append(state.current) if state.phase=='running' and state.total else None)
    original=w.refresh_images
    def refresh():
        if w.project['images']:committed.append(list(counts))
        original()
    monkeypatch.setattr(w,'refresh_images',refresh)
    w.import_paths([f'{i}.tif' for i in range(30)]);wait()
    assert counts==list(range(1,31))
    assert committed and committed[0]==counts
    assert len(w.project['images'])==30 and w.progress.phase=='complete' and not errors


def test_progress_text_repaints_without_relayout_of_either_sidebar(workbench):
    w,app,wait,errors=workbench
    w.task=object();w.task_kind='preparation';w.task_title='准备影像';w.task_stage=''
    w.progress_presentation.begin();w.update_controls();w.task_progress(1,100,'准备影像 1/100');settle(app)
    spy=PanelEvents(w);app.installEventFilter(spy)
    try:
        for i in range(2,101):
            w.task_progress(i,100,f'准备影像 {i}/100');app.processEvents()
        assert not spy.events
        assert w.progress_count.text()=='块 100 / 100'
        assert w.task_text.accessibleName()==w.task_text.text()
    finally:
        app.removeEventFilter(spy);w.task=None;w.task_kind=None
    assert not errors


def test_cancelling_fast_import_discards_pending_display_updates_and_result(workbench,monkeypatch):
    from geoforma.controllers import images
    w,app,wait,errors=workbench
    monkeypatch.setattr(images,'inspect_source',lambda path:fake_image(path,path))
    monkeypatch.setattr(images,'make_recipe',lambda *args:{'bands':[1,2,3]})
    w.import_paths([f'{i}.tif' for i in range(30)])
    until(app,lambda:w.progress.model.state.current>=2)
    before=w.progress.model.state.current;w.cancel();wait()
    assert not w.project['images'] and w.progress.phase=='cancelled'
    assert w.progress.model.state.current==before and not errors


def test_cached_preparation_batch_does_not_enable_buttons_between_images(workbench,monkeypatch):
    w,app,wait,errors=workbench
    w.project['images']=[fake_image(str(i),f'folder/{i}.tif') for i in range(30)]
    w.refresh_images();w.images.setCurrentRow(0);w.raster_list_sizer.settle();settle(app)
    w.images.verticalScrollBar().setValue(w.images.verticalScrollBar().maximum()//2)
    scroll=w.images.verticalScrollBar().value();items=[w.images.item(i) for i in range(30)]
    monkeypatch.setattr(w,'ensure_model_resources',lambda:True)
    w.service.preprocess=lambda image,config,bounds,task:dict(count=9,hits=9,checkpoint=config['checkpoint'],device='cpu',execution='native')
    changes=[];resets=[];saves=[]
    monkeypatch.setattr(w,'autosave',lambda:saves.append(True))
    class EnabledSpy(QObject):
        def eventFilter(self,obj,event):
            if obj is w.import_button and event.type()==QEvent.Type.EnabledChange:changes.append(obj.isEnabled())
            return False
    spy=EnabledSpy();app.installEventFilter(spy)
    w.images.model().modelReset.connect(lambda:resets.append(True))
    try:
        w.auto_prepare=True;w.queue_preparation();wait()
        assert changes==[False,True]
        assert len(saves)==1 and not resets
        assert [image['ready'] for image in w.project['images']]==[True,True]+[False]*28
        assert all(w.images.item(i) is item for i,item in enumerate(items))
        assert w.images.verticalScrollBar().value()==scroll
    finally:app.removeEventFilter(spy)
    assert not errors
