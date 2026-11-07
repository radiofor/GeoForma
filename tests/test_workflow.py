import copy,threading
from types import SimpleNamespace
import pytest
from geoforma.workflow import PreparationQueue,full_bounds,tile_count,preparation_signature,fully_prepared,check_cache_space
from geoforma.inference.engine import ModelEngine


def image(identifier='one'):
    return {'id':identifier,'width':1958,'height':1957,'transform':[1,0,0,0,-1,0],
            'fingerprint':'source','model_recipe':{'bands':[1,2,3],'ranges':[[0,255]]*3},'ready':False}


def test_queue_skips_completed_and_unknown_bands_and_can_pause(tmp_path):
    model={'variant':'vit_b','device':'cuda','checkpoint':str(tmp_path/'model.pth')}
    first,second,third=image(),image('two'),image('three')
    first.update(ready=True,prepared_full_signature=preparation_signature(first,model));second['model_recipe']=None
    project={'images':[first,second,third],'model':model};queue=PreparationQueue();queue.add(['gone','one','two','three','three'])
    queue.paused=True;assert queue.next(project) is None and len(queue.ids)==4
    queue.paused=False;assert queue.next(project) is third;assert second['preparation_state']=='bands_required'
    assert queue.next(project) is None


def test_full_readiness_invalidates_model_recipe_source_and_weight_change(tmp_path):
    weight=tmp_path/'model.pth';weight.write_bytes(b'weight');model={'variant':'vit_b','device':'cuda','checkpoint':str(weight)}
    im=image();im.update(ready=True,prepared_full_signature=preparation_signature(im,model))
    assert full_bounds(im)==[0,0,1958,1957] and tile_count(im)==9 and fully_prepared(im,model)
    assert fully_prepared(im,dict(model,device='cpu'))
    for key,value in [('fingerprint','changed'),('transform',[2,0,0,0,-2,0]),('model_recipe',{'bands':[3,2,1]})]:
        altered=copy.deepcopy(im);altered[key]=value;assert not fully_prepared(altered,model)
    assert not fully_prepared(im,dict(model,variant='vit_l'))
    weight.write_bytes(b'other-weight');assert not fully_prepared(im,model)
    legacy=dict(im,prepared_full_signature=None);assert not fully_prepared(legacy,model)


def test_preprocessing_uses_entire_grid_even_if_caller_passes_a_view(tmp_path,monkeypatch):
    monkeypatch.setenv('GEOFORMA_DATA_DIR',str(tmp_path))
    calls=[]
    backend=SimpleNamespace(config={'device':'cpu'},key=lambda im,w:str(tuple(w)),encode=lambda im,w,rgb:(calls.append((w,rgb)) or False))
    engine=ModelEngine();engine.backend=backend;engine.prepare_backend=lambda *a:None
    task=SimpleNamespace(check=lambda:None,signals=SimpleNamespace(progress=SimpleNamespace(emit=lambda *a:None)))
    answer=engine.preprocess(image(),{'checkpoint':'test'},[800,800,10,10],task)
    assert answer['bounds']==[0,0,1958,1957] and answer['count']==9
    assert calls[0]==((-128,-128,1024,1024),None) and calls[-1][0]==(1408,1408,1024,1024)


def test_disk_budget_blocks_huge_image_before_encoding_but_allows_cache_hits(tmp_path,monkeypatch):
    import geoforma.workflow as workflow
    monkeypatch.setattr(workflow.shutil,'disk_usage',lambda p:SimpleNamespace(free=5*1024**3))
    with pytest.raises(RuntimeError,match='缓存空间不足'):check_cache_space(tmp_path,100000)
    assert check_cache_space(tmp_path,0)==0


def test_cached_work_needs_no_disk_space_even_below_reserve(tmp_path,monkeypatch):
    import geoforma.workflow as workflow
    monkeypatch.setattr(workflow.shutil,'disk_usage',lambda p:SimpleNamespace(free=10))
    assert check_cache_space(tmp_path,0)==0
    with pytest.raises(RuntimeError,match='缓存空间不足'):check_cache_space(tmp_path,1)


def test_unusable_existing_feature_checks_space_before_replacement(tmp_path,monkeypatch):
    import geoforma.workflow as workflow
    from geoforma.feature_cache import check_rewrite_space
    path=tmp_path/'bad.pt';calls=[]
    monkeypatch.setattr(workflow,'check_cache_space',lambda root,count,size:calls.append((root,count,size)))
    check_rewrite_space(tmp_path,path,123);assert not calls
    path.write_bytes(b'invalid')
    check_rewrite_space(tmp_path,path,123);assert calls==[(tmp_path,1,123)]


def test_large_preflight_reuses_single_directory_scan(tmp_path,monkeypatch):
    import geoforma.workflow as workflow
    import geoforma.inference.engine as module
    monkeypatch.setenv('GEOFORMA_DATA_DIR',str(tmp_path))
    folder=tmp_path/'cache'/'features';folder.mkdir(parents=True)
    (folder/(f'{0:064x}'+'.pt')).write_bytes(b'cached')
    monkeypatch.setattr(workflow,'tile_count',lambda im:4097)
    monkeypatch.setattr(module,'tiles',lambda *args:((i,0,1,1) for i in range(4097)))
    budgets=[];monkeypatch.setattr(workflow,'check_cache_space',lambda root,count,size:budgets.append(count))
    backend=SimpleNamespace(config={'device':'cpu'},key=lambda im,w:f'{w[0]:064x}',encode=lambda *a:False)
    engine=ModelEngine();engine.backend=backend;engine.prepare_backend=lambda *a:None
    task=SimpleNamespace(check=lambda:None,signals=SimpleNamespace(progress=SimpleNamespace(emit=lambda *a:None)))
    engine.preprocess(image(),{'checkpoint':'test'},None,task)
    assert budgets==[4096,4096]


def test_choice_prefers_explicit_prompts_then_model_score():
    from geoforma.workflow import best_choice,prompt_misses
    from shapely.geometry import box,mapping
    choices=[{'geometry':mapping(box(0,0,100,100)),'score':.99},
             {'geometry':mapping(box(10,10,30,30)),'score':.85},
             {'geometry':mapping(box(10,10,35,35)),'score':.9}]
    points=[[20,20,1],[25,25,1],[90,90,0]]
    assert prompt_misses(choices[0]['geometry'],points)==1
    assert best_choice(choices,points)==2
    assert best_choice(choices,[])==0 and best_choice([],points)==-1

