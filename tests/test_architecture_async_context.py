import threading,time,copy
import numpy as np
from PySide6.QtCore import QSignalBlocker
from shapely.geometry import box,mapping
from test_workbench import workbench,fake_image


def spin(app,predicate):
    limit=time.monotonic()+5
    while not predicate() and time.monotonic()<limit:app.processEvents();time.sleep(.003)
    assert predicate()


def images(w):
    rows=[fake_image('one'),fake_image('two')]
    for image in rows:image['ready']=True
    w.project['images']=rows;w.refresh_images();w.images.setCurrentRow(0)
    w.service.activate_project=lambda *args:False
    return rows


def test_busy_image_selection_is_restored_and_late_results_cannot_cross_images(workbench):
    w,app,wait,errors=workbench;rows=images(w);started=threading.Event();release=threading.Event()
    def predict(image,config,request,task):
        started.set();release.wait(4)
        task.signals.preview.emit(dict(mask=np.ones((4,4),np.uint8),window=request['window']))
        return dict(choices=[{'geometry':mapping(box(1,1,20,20)),'edge':False,'score':.9}],window=request['window'],key='test',cache_hit=True,device='cpu')
    w.service.predict=predict;w.add_point(10,10,1);w.predict()
    try:
        spin(app,started.is_set);w.images.setCurrentRow(1)
        assert w.image is rows[0] and w.images.currentRow()==0
        with QSignalBlocker(w.images):w.images.setCurrentRow(1)
        w._activate_image(1);release.set();wait()
        assert w.image is rows[1] and not w.draft.get('geometry') and not w.project['labels']
        assert rows[0]['mode_sessions']['individual']['draft']['points']==[[10,10,1]] and not errors
    finally:release.set()


def test_completion_hook_can_start_a_new_task_without_losing_its_state(workbench):
    w,app,wait,errors=workbench;started=threading.Event();release=threading.Event();values=[]
    def second(task):started.set();release.wait(4);return 'second'
    w.run('first',lambda task:'first',values.append,kind='export',on_finished=lambda:w.run('second',second,values.append,kind='history'))
    try:
        spin(app,started.is_set)
        assert w.task_kind=='history' and w.task_title=='second' and w.task is not None
        release.set();wait();assert values==['first','second'] and not errors
    finally:release.set()


def test_large_undo_is_cancellable_without_partial_label_changes(workbench,monkeypatch):
    import geoforma.label_history as history
    w,app,wait,errors=workbench;images(w)
    w.project['labels']=[dict(id=str(i),image_id='one',class_id=1,status='confirmed',geometry=mapping(box(i*3,0,i*3+1,1))) for i in range(500)]
    w.label_undo=[[(str(i),None,i)] for i in range(299,500)]
    w.refresh_labels();wait();before=copy.deepcopy(w.project['labels']);undo=copy.deepcopy(w.label_undo)
    started=threading.Event();release=threading.Event();original=history.replay_all
    def replay(*args):
        started.set();release.wait(4);args[-1].check();return original(*args)
    monkeypatch.setattr(history,'replay_all',replay)
    tick=time.monotonic();w.undo_all_labels()
    try:
        assert time.monotonic()-tick<.75
        spin(app,started.is_set);w.cancel();release.set();wait()
        assert w.project['labels']==before and w.label_undo==undo
        w.undo_all_labels();wait()
        assert len(w.project['labels'])==299 and not w.label_undo and len(w.label_redo)==201
        w.redo_label();wait();assert len(w.project['labels'])==300 and not errors
    finally:release.set()
