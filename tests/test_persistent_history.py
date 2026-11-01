import os,copy,time
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtWidgets import QApplication
from shapely.geometry import box,mapping,shape
from geoforma.window import MainWindow
from geoforma.controllers.projects import ProjectWorkflow
from geoforma.storage import load_project,save_project,project_snapshot


def image(identifier,path):
    return dict(id=identifier,path=str(path),name=path.name,width=1000,height=1000,ready=True,
                model_recipe=None,display_recipe=None,bands=3,dtypes=['uint8'],crs='EPSG:3857',source_files=1,
                transform=[1,0,0,0,-1,1000],fingerprint=identifier)


@pytest.fixture
def workbench(tmp_path,monkeypatch):
    monkeypatch.setenv('GEOFORMA_DATA_DIR',str(tmp_path/'data'))
    app=QApplication.instance() or QApplication([]);w=MainWindow(auto_prepare=False)
    w.autosave=lambda:None;w.auto_apply.setChecked(False);w.project_path=tmp_path/'history.geoforma.json'
    w.project['images']=[image('image',tmp_path/'source.tif')];w.refresh_images();w.images.setCurrentRow(0)
    errors=[];w.error=errors.append
    yield w,app,tmp_path,errors
    w.image=None;w.dirty=False;w.close()
    deadline=time.monotonic()+4
    while (w.candidate_task or w.autosave_task) and time.monotonic()<deadline:app.processEvents();time.sleep(.002)
    app.processEvents()


def reopen(w,errors):
    w.save();assert not errors
    w.open_project(w.project_path);assert not errors


def create_label(w,x=100):
    w.draft={'geometry':mapping(box(x,100,x+50,150)),'points':[],'box':None,'window':[-128,-128,1024,1024]}
    w.confirm();return w.project['labels'][-1]['id']


def test_points_boxes_and_redo_survive_save_and_reopen(workbench):
    w,app,tmp_path,errors=workbench
    w.add_point(110,110,1);w.add_point(140,140,0);w.add_box([100,100,180,180]);w.undo_context()
    assert len(w.prompt_undo)==2 and len(w.prompt_redo)==1 and w.draft['box'] is None
    reopen(w,errors)
    assert len(w.prompt_undo)==2 and len(w.prompt_redo)==1
    w.redo_context();assert w.draft['box']==[100,100,180,180]
    w.undo_context();w.undo_context();assert w.draft['points']==[[110,110,1]] and not w.project['labels']


def test_automatic_candidate_prompt_history_survives_project_reopen(workbench):
    w,app,tmp_path,errors=workbench
    candidate=dict(id='candidate',image_id='image',annotation_mode='automatic',status='candidate',class_id=None,
                   geometry=mapping(box(100,100,180,180)),window=[0,0,1024,1024])
    w.project['labels']=[candidate];w.select_label('candidate');w.edit_selected(locate=False)
    w.set_tool('negative');w.add_point(120,120,1);w.add_point(170,170,0);w.undo_context()
    assert w.draft['points']==[[120,120,1]] and len(w.prompt_redo)==1
    reopen(w,errors)
    assert w.mode_index==0 and w.draft['base_id']=='candidate' and w.draft['pending']
    assert w.draft['points']==[[120,120,1]] and len(w.prompt_redo)==1
    assert w.view.selected_mode=='negative'
    w.image['ready']=True;w.update_controls();assert w.mode_actions['negative'].isEnabled()
    w.redo_context();assert w.draft['points']==[[120,120,1],[170,170,0]]
    assert w.draft['points']==[[120,120,1],[170,170,0]]


def test_individual_legacy_candidate_saves_undo_survive_project_reopen(workbench):
    w,app,tmp_path,errors=workbench
    candidates=[dict(id=str(i),image_id='image',annotation_mode='automatic',status='candidate',class_id=None,
                     geometry=mapping(box(100+i*120,100,180+i*120,180)),window=[0,0,1024,1024]) for i in range(3)]
    w.project['labels']=copy.deepcopy(candidates);w.refresh_labels()
    from test_background_activity import until
    until(app,lambda:w.candidate_task is None and w.candidate_key==w.candidate_signature())
    for candidate in candidates:
        w.select_label(candidate['id']);w.edit_selected(locate=False);w.confirm()
    assert len(w.label_undo)==3 and all(l['status']=='confirmed' for l in w.project['labels'])
    reopen(w,errors);assert len(w.label_undo)==3
    w.undo_all_labels();assert [l['id'] for l in w.project['labels']]==[l['id'] for l in candidates]
    assert all(l['status']=='candidate' and shape(l['geometry']).equals(shape(old['geometry'])) for l,old in zip(w.project['labels'],candidates))
    for _ in candidates:w.redo_label()
    assert all(l['status']=='confirmed' for l in w.project['labels'])


def test_cleared_points_can_be_restored_after_empty_draft_reopens(workbench):
    w,app,tmp_path,errors=workbench;saved_id=create_label(w,20)
    w.add_point(120,120,1);w.add_point(170,170,0);points=copy.deepcopy(w.draft['points'])
    w.clear_points();w.predict()  # Empty prompt group clears its result without model inference.
    assert not w.draft['pending'] and not w.draft['points']
    reopen(w,errors);assert w.undo_prompt_action.isEnabled()
    w.undo_context();assert w.draft['points']==points and w.project['labels'][0]['id']==saved_id
    w.redo_context();assert not w.draft['points'] and w.project['labels'][0]['id']==saved_id


def test_label_save_delete_undo_and_redo_survive_project_reopen(workbench):
    w,app,tmp_path,errors=workbench;identifier=create_label(w);geometry=copy.deepcopy(w.project['labels'][0]['geometry'])
    w.select_label(identifier);w.delete_selected();w.undo_label()
    assert len(w.label_undo)==1 and len(w.label_redo)==1
    reopen(w,errors);assert len(w.label_undo)==1 and len(w.label_redo)==1
    w.redo_context();assert not w.project['labels']
    w.undo_context();assert w.project['labels'][0]['id']==identifier and shape(w.project['labels'][0]['geometry']).equals(shape(geometry))
    w.undo_context();assert not w.project['labels']


def test_whole_history_undo_keeps_redo_steps_after_project_reopen(workbench):
    w,app,tmp_path,errors=workbench;first=create_label(w,100);second=create_label(w,300)
    w.undo_all_labels()
    assert not w.project['labels'] and not w.label_undo and len(w.label_redo)==2
    reopen(w,errors);assert not w.label_undo and len(w.label_redo)==2
    w.redo_context();assert [label['id'] for label in w.project['labels']]==[first]
    w.redo_context();assert [label['id'] for label in w.project['labels']]==[first,second] and not errors


def test_new_and_legacy_label_edits_share_history_after_reopen(workbench):
    w,app,tmp_path,errors=workbench;manual_id=create_label(w,20)
    candidate=dict(id='candidate',image_id='image',annotation_mode='automatic',status='candidate',class_id=None,
                   geometry=mapping(box(200,200,260,260)),source='automatic',window=[-128,-128,1024,1024])
    w.project['labels'].append(candidate);w.select_items('labels',['candidate']);w.edit_selected(locate=False);w.confirm()
    reopen(w,errors);assert w.mode_index==0 and len(w.label_undo)==2
    w.undo_context();assert next(l for l in w.project['labels'] if l['id']=='candidate')['status']=='candidate'
    assert next(l for l in w.project['labels'] if l['id']==manual_id)['status']=='confirmed'
    w.undo_context()
    assert [l['id'] for l in w.project['labels']]==['candidate'] and len(w.label_redo)==2


def test_each_image_keeps_its_own_prompt_redo_after_save(workbench):
    w,app,tmp_path,errors=workbench
    w.add_point(120,120,1);w.add_point(150,150,0);w.undo_context()
    w.project['images'].append(image('other',tmp_path/'other.tif'));w.refresh_images();w.images.setCurrentRow(1)
    w.add_point(300,300,1);w.undo_context();reopen(w,errors)
    assert w.image['id']=='other' and not w.draft['points'] and len(w.prompt_redo)==1
    w.redo_context();assert w.draft['points']==[[300,300,1]]
    w.images.setCurrentRow(0);w.redo_context();assert w.draft['points']==[[120,120,1],[150,150,0]]


def test_autosave_history_snapshot_is_not_changed_by_new_operations(workbench):
    w,app,tmp_path,errors=workbench
    w.add_point(120,120,1);w.add_point(150,150,0);w.undo_context()
    ProjectWorkflow.autosave(w);w.redo_context();w.add_point(170,170,1)
    deadline=time.monotonic()+4
    while w.autosave_task and time.monotonic()<deadline:app.processEvents();time.sleep(.002)
    assert not w.autosave_task and not errors
    saved=load_project(str(w.project_path)+'.autosave');session=saved['images'][0]['mode_sessions']['individual']
    assert session['draft']['points']==[[120,120,1]] and len(session['redo'])==1 and len(session['undo'])==1


def test_history_snapshot_detaches_stacks_and_legacy_projects_still_open(workbench):
    w,app,tmp_path,errors=workbench;create_label(w);w.capture_workspace();snapshot=project_snapshot(w.project)
    w.project['history']['labels']['individual']['undo'].clear()
    assert len(snapshot['history']['labels']['individual']['undo'])==1
    w.project.pop('history');save_project(w.project,w.project_path);w.open_project(w.project_path)
    assert not errors and not w.label_undo and not w.label_redo


def test_malformed_cross_mode_history_is_rejected_before_restoring_labels(workbench):
    w,app,tmp_path,errors=workbench;identifier=create_label(w)
    w.project['history']={'schema':1,'labels':{'automatic':{'undo':[[[identifier,None,0]]],'redo':[]}}}
    save_project(w.project,w.project_path)
    with pytest.raises(ValueError,match='跨标注模式'):load_project(w.project_path)
