import os,copy,time,threading
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtWidgets import QApplication
from shapely.geometry import box,mapping
from geoforma.window import MainWindow


@pytest.fixture
def workbench():
    app=QApplication.instance() or QApplication([]);w=MainWindow(auto_prepare=False);w.autosave=lambda:None
    w.ensure_model_resources=lambda:True
    w.auto_apply.setChecked(False)
    w.image={'id':'image','width':1000,'height':1000,'ready':True,'model_recipe':None,'display_recipe':None}
    w.project['labels']=[dict(id='saved',image_id='image',annotation_mode='individual',status='confirmed',class_id=1,
                             geometry=mapping(box(20,20,80,80)),points=[[30,30,1]],window=[-128,-128,1024,1024])]
    yield w,app
    w.image=None;w.dirty=False;w.close();app.processEvents()


def prediction(request):
    return dict(choices=[dict(geometry=mapping(box(100,100,200,200)),score=.9,edge=False)],
                window=request['window'],key='test',cache_hit=True,device='cpu')


def wait(app,condition):
    deadline=time.monotonic()+4
    while not condition() and time.monotonic()<deadline:app.processEvents();time.sleep(.002)
    assert condition()


def test_clear_all_points_is_one_undoable_operation_and_keeps_saved_labels(workbench):
    w,app=workbench;before=copy.deepcopy(w.project['labels'])
    for i in range(20):w.add_point(110+i,120+i,i%2)
    points=copy.deepcopy(w.draft['points']);undo_count=len(w.prompt_undo);w.selected_points={0,5,19}
    assert w.clear_points_button.isEnabled()
    w.clear_points_button.click()
    assert not w.draft['points'] and not w.selected_points and len(w.prompt_undo)==undo_count+1
    assert w.project['labels']==before and not w.label_undo and not w.clear_points_button.isEnabled()
    w.undo_context();assert w.draft['points']==points and w.project['labels']==before
    w.redo_context();assert not w.draft['points'] and w.project['labels']==before


def test_clear_keeps_box_and_manual_apply_uses_no_points(workbench):
    w,app=workbench;before=copy.deepcopy(w.project['labels']);calls=[]
    w.add_box([100,100,250,250]);w.add_point(120,120,1);w.add_point(240,240,0)
    w.service.predict=lambda image,config,request,task:(calls.append(copy.deepcopy(request)) or prediction(request))
    w.run=lambda title,work,done,**kw:done(work(None))
    w.predict();w.clear_points()
    assert w.draft['box']==[100,100,250,250] and w.draft['pending'] and not w.confirm_button.isEnabled()
    assert len(calls)==1
    w.predict();assert calls[-1]['points']==[] and calls[-1]['box']==[100,100,250,250]
    assert w.project['labels']==before


def test_clearing_during_automatic_prediction_discards_stale_mask(workbench):
    w,app=workbench;before=copy.deepcopy(w.project['labels']);started=threading.Event();release=threading.Event()
    def predict(image,config,request,task):
        started.set();release.wait(3);return prediction(request)
    w.service.predict=predict;w.auto_apply.setChecked(True);w.add_point(120,120,1);w.add_point(230,230,0)
    try:
        wait(app,started.is_set);assert w.clear_points_button.isEnabled();w.clear_points_button.click()
        assert not w.draft['points'];release.set()
        wait(app,lambda:w.task is None and not w.draft.get('pending'))
        assert not w.draft.get('geometry') and not w.confirm_button.isEnabled() and w.project['labels']==before
    finally:release.set()


def test_clear_points_does_not_modify_saved_target_being_edited(workbench):
    w,app=workbench;before=copy.deepcopy(w.project['labels']);w.select_label('saved');w.edit_selected(locate=False)
    seed=copy.deepcopy(w.draft['seed_geometry']);w.add_point(30,30,1);w.add_point(70,70,0);w.clear_points()
    assert w.draft['base_id']=='saved' and w.draft['seed_geometry']==seed and not w.draft['points']
    assert w.project['labels']==before and not w.label_undo


def test_removed_mode_cannot_interrupt_clear_points(workbench):
    w,app=workbench;w.add_point(120,120,1)
    assert not hasattr(w,'tabs')
    assert w.mode_index==0 and not w.clear_points_button.isHidden() and w.clear_points_button.isEnabled()
    w.clear_points();assert not w.draft['points']
