"""Deferred editing must not start after its drawing session is gone."""
import pytest
from test_reshape import workbench,raster_image,OUT


def capture_deferred(window,monkeypatch):
    callbacks=[]
    def defer(callback,allow_prompt_changes=False):
        callbacks.append(callback)
        window.pending_prefetch_work=(window.annotation_context(),callback,allow_prompt_changes)
        return True
    monkeypatch.setattr(window,'defer_for_prefetch',defer)
    return callbacks


@pytest.mark.parametrize('change', ['cancel','context'])
def test_single_reshape_does_not_resume_after_session_ends(workbench,monkeypatch,change):
    w,_,_=workbench;callbacks=capture_deferred(w,monkeypatch)
    w.selected_id='target';w.selected_ids={'target'};w.begin_reshape()
    assert w.reshape_session and w.reshape_session['target']=='label'
    for point in OUT:w.add_reshape_point(*point)
    w.finish_reshape();assert len(callbacks)==1
    if change=='cancel':
        w.cancel_reshape();assert w.pending_prefetch_work is None
    else:w.project_epoch+=1
    calls=[];monkeypatch.setattr(w,'run',lambda *args,**kwargs:calls.append(args))
    callbacks[0]()
    assert not calls


@pytest.mark.parametrize('automatic', [False,True])
@pytest.mark.parametrize('change', ['stroke','alternate','fill'])
def test_reshape_does_not_resume_with_outdated_stroke_or_options(workbench,monkeypatch,automatic,change):
    w,_,_=workbench;callbacks=capture_deferred(w,monkeypatch)
    if not automatic:w.selected_id='target';w.selected_ids={'target'}
    w.begin_reshape(auto=automatic)
    for point in OUT:w.add_reshape_point(*point)
    w.finish_reshape();assert len(callbacks)==1
    if change=='stroke':w.reshape_session['stroke'].append([1,1])
    elif change=='alternate':w.reshape_session['alternate']=not w.reshape_session['alternate']
    else:w.fill_holes.setChecked(not w.fill_holes.isChecked())
    calls=[];monkeypatch.setattr(w,'run',lambda *args,**kwargs:calls.append(args))
    callbacks[0]()
    assert not calls


@pytest.mark.parametrize('change', ['cancel','context','single'])
def test_manual_draw_does_not_resume_after_context_changes(workbench,monkeypatch,change):
    w,_,_=workbench;callbacks=capture_deferred(w,monkeypatch)
    w.image['width']=1000;w.image['height']=1000;w.set_tool('draw_polygon')
    for point in ((10,10),(700,10),(700,700),(10,700)):w.add_manual_vertex(*point)
    w.finish_manual_polygon();assert len(callbacks)==1
    if change=='cancel':w.cancel_manual_polygon()
    elif change=='context':w.project_epoch+=1
    else:w.single_polygon.setChecked(not w.single_polygon.isChecked())
    calls=[];monkeypatch.setattr(w,'run',lambda *args,**kwargs:calls.append(args))
    callbacks[0]()
    assert not calls


def test_manual_draw_resumes_when_still_current(workbench,monkeypatch):
    w,_,_=workbench;callbacks=capture_deferred(w,monkeypatch)
    w.image['width']=1000;w.image['height']=1000;w.set_tool('draw_polygon')
    for point in ((10,10),(700,10),(700,700),(10,700)):w.add_manual_vertex(*point)
    w.finish_manual_polygon();assert len(callbacks)==1
    calls=[];monkeypatch.setattr(w,'run',lambda *args,**kwargs:calls.append(args))
    callbacks[0]()
    assert len(calls)==1
