"""Selected-image preparation follows navigation instead of traversing the catalog."""
import threading
from pathlib import Path
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from geoforma.workflow import preparation_window
from test_workbench import workbench,fake_image
from test_background_activity import until


def setup_queue(w,monkeypatch,count=6):
    images=[fake_image(str(i),f'folder-{i}/{i}.tif') for i in range(count)]
    w.project['images']=images;w.refresh_images();w.images.setCurrentRow(0)
    monkeypatch.setattr(w,'ensure_model_resources',lambda:True)
    return images


def result(config):return dict(count=9,hits=9,checkpoint=config['checkpoint'],device='cpu',execution='native')


def test_window_has_no_wrap_and_handles_unknown_selection():
    images=[{'id':str(i)} for i in range(4)]
    assert preparation_window(images,images[1])==(images[1],images[2])
    assert preparation_window(images,images[-1])==(images[-1],)
    assert preparation_window(images,None)==preparation_window(images,{'id':'gone'})==()


def test_switch_prepares_only_new_pair_and_reuses_completed_images(workbench,monkeypatch):
    w,app,wait,errors=workbench;images=setup_queue(w,monkeypatch);calls=[]
    w.service.preprocess=lambda image,config,bounds,task:(calls.append(image['id']) or result(config))
    w.auto_prepare=True;w.queue_preparation();wait();assert calls==['0','1']
    w.images.setCurrentRow(1);wait();assert calls==['0','1','2']
    w.images.setCurrentRow(4);wait();assert calls==['0','1','2','4','5']
    w.images.setCurrentRow(0);wait();assert calls==['0','1','2','4','5']
    w.images.setCurrentRow(5);wait();assert calls==['0','1','2','4','5']
    assert not images[3]['ready'] and not w.preparation.ids and not errors


def test_ready_image_can_predict_and_save_while_next_image_is_prefetched(workbench,monkeypatch):
    from shapely.geometry import box,mapping
    from geoforma.workflow import preparation_signature
    w,app,wait,errors=workbench;images=setup_queue(w,monkeypatch,2);calls=[]
    images[0]['ready']=True;images[0]['prepared_full_signature']=preparation_signature(images[0],w.project['model'])
    first=threading.Event();resume=threading.Event();second=threading.Event();finish=threading.Event()
    def prepare(image,config,bounds,task):
        calls.append('prepare')
        if calls.count('prepare')==1:
            first.set();assert resume.wait(5);task.check()
        else:second.set();assert finish.wait(5);task.check()
        return result(config)
    def predict(image,config,request,task):
        calls.append('predict')
        return {'choices':[{'geometry':mapping(box(100,100,180,180)),'score':.9,'edge':False}],
                'window':request['window'],'key':'cached','cache_hit':True,'device':'cpu'}
    w.service.preprocess=prepare;w.service.predict=predict;w.auto_prepare=True;w.auto_apply.setChecked(True)
    try:
        w.queue_preparation();until(app,first.is_set)
        assert w.mode_actions['positive'].isEnabled() and w.auto_apply.isEnabled()
        w.add_point(140,140,1);until(app,lambda:w.task.cancel_event.is_set())
        resume.set();until(app,second.is_set)
        assert calls==['prepare','predict','prepare'] and w.draft.get('geometry')
        assert w.confirm_button.isEnabled();w.confirm();assert len(w.project['labels'])==1
        finish.set();wait();assert images[1]['ready'] and not errors
    finally:resume.set();finish.set()


@pytest.mark.parametrize('cooperative',[True,False])
@pytest.mark.parametrize('return_to_start',[False,True])
def test_switch_cancels_obsolete_work_without_pausing_new_pair(workbench,monkeypatch,cooperative,return_to_start):
    w,app,wait,errors=workbench;images=setup_queue(w,monkeypatch);started=threading.Event();release=threading.Event();calls=[]
    def prepare(image,config,bounds,task):
        calls.append(image['id'])
        if len(calls)==1:
            started.set();assert release.wait(5)
            if cooperative:task.check()
        return result(config)
    w.service.preprocess=prepare;w.auto_prepare=True
    try:
        w.queue_preparation();until(app,started.is_set);old=w.task
        w.images.setCurrentRow(3)
        assert old.cancel_event.is_set() and list(w.preparation.ids)==['3','4']
        assert images[1].get('preparation_state')!='queued'
        if return_to_start:
            w.images.setCurrentRow(0);assert list(w.preparation.ids)==['0','1']
        release.set();wait()
        assert calls==(['0','0','1'] if return_to_start else ['0','3','4'])
        assert not w.preparation.paused and not w.last_error and not errors
        assert all(im.get('preparation_state')!='preparing' for im in images)
        assert [im['id'] for im in images if im['ready']]==(['0','1'] if return_to_start else ['3','4'])
    finally:release.set()


def test_directory_changes_with_selection_and_is_readonly_and_copyable(workbench,monkeypatch):
    w,app,wait,errors=workbench;images=setup_queue(w,monkeypatch)
    directory=w.image_info.directory
    assert directory.isReadOnly() and directory.text()==str(Path(images[0]['path']).resolve().parent)
    w.images.setCurrentRow(2)
    expected=str(Path(images[2]['path']).resolve().parent)
    assert directory.text()==expected and directory.textCursor().position()==0
    directory.setFocus();directory.selectAll();QTest.keyClick(directory,Qt.Key.Key_C,Qt.KeyboardModifier.ControlModifier)
    assert app.clipboard().text()==expected
    geometry=w.image_info.geometry();w.refresh_info();assert w.image_info.geometry()==geometry
    w.image=None;w.refresh_info();assert directory.text()=='—' and not errors
