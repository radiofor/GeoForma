import os,copy,time,json
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import numpy as np
import pytest
from shapely.geometry import box,mapping,shape,MultiPolygon,Polygon,Point
from geoforma.reshape import reshape_intent,reshape_patch,reshape_raster
from geoforma.domain import new_project


OUT=[[22,28],[22,34],[28,34],[28,28]]
IN=[[22,34],[22,28],[28,28],[28,34]]
G=mapping(box(20,20,30,30))


@pytest.mark.parametrize('stroke,area,added,removed',[(OUT,124,24,0),(IN,88,0,12)])
def test_raster_reshape_expands_and_cuts(stroke,area,added,removed):
    result=reshape_patch(reshape_intent(G,stroke),{'width':100,'height':100})
    g=shape(result['geometry']);assert g.area==area and g.is_valid
    assert result['added_pixels']==added and result['removed_pixels']==removed


def test_diagonal_stroke_preserves_vector_edges_without_changing_other_boundary():
    stroke=[[22,28],[23.2,34.3],[28,28]]
    intent=reshape_intent(G,stroke)
    result=reshape_patch(intent,{'width':100,'height':100})
    g=shape(result['geometry'])
    assert g.equals(shape(intent['candidate']))
    assert g.boundary.distance(Point(23.2,34.3))<1e-10
    assert g.intersection(box(0,0,100,29)).equals(shape(G).intersection(box(0,0,100,29)))


def test_unrelated_parts_and_holes_are_unchanged():
    part=box(20,20,30,30).difference(box(24,24,26,26));sibling=box(60,60,70,70)
    result=reshape_patch(reshape_intent(mapping(MultiPolygon([part,sibling])),OUT),{'width':100,'height':100})
    g=shape(result['geometry']);assert g.intersection(box(50,50,80,80)).equals(sibling)
    target=next(p for p in g.geoms if p.bounds[0]<50);assert len(target.interiors)==1
    assert box(24,24,26,26).equals(Polygon(target.interiors[0]))


@pytest.mark.parametrize('stroke',[[[40,40],[50,50]],[[25,25],[25,40]],[[20,20],[30,20]],[[22,28],[28,34],[22,34],[28,28]]])
def test_ambiguous_or_invalid_lines_do_not_modify_geometry(stroke):
    original=copy.deepcopy(G)
    with pytest.raises(ValueError):reshape_intent(G,stroke)
    assert G==original


def test_full_pixel_box_nodata_and_existing_labels_limit_additions():
    intent=reshape_intent(G,OUT);x,y,w,h=intent['window'];valid=np.ones((h,w),bool)
    valid[max(0,31-y),:]=False
    blocker=mapping(box(26,30,28,34))
    result=reshape_patch(intent,{'width':100,'height':100},valid,[blocker],[20,20,30,33.75])
    g=shape(result['geometry']);assert g.bounds[3]==pytest.approx(33.75) and g.intersection(shape(blocker)).area==0
    assert g.intersection(box(0,31,100,32)).area==0


def test_single_polygon_and_alternate_boundary_are_explicit():
    multi=mapping(MultiPolygon([box(20,20,30,30),box(60,60,64,64)]))
    result=reshape_patch(reshape_intent(multi,OUT),{'width':100,'height':100},single=True)
    assert result['geometry']['type']=='Polygon'
    smaller=reshape_patch(reshape_intent(G,IN,True),{'width':100,'height':100})
    assert shape(smaller['geometry']).area==12


def test_single_polygon_reshape_ignores_old_model_points(workbench):
    w,app,_=workbench
    w.single_polygon.setChecked(True);w.smooth_enabled.setChecked(False)
    w.project['labels'][0]['geometry']=mapping(MultiPolygon([box(20,20,30,30),box(60,60,64,64)]))
    w.project['labels'][0]['points']=[[62,62,1]];w.refresh_labels()
    w.begin_reshape(auto=True)
    for x,y in OUT:w.add_reshape_point(x,y)
    w.finish_reshape();deadline=time.monotonic()+8
    while w.task and time.monotonic()<deadline:app.processEvents();time.sleep(.002)
    assert w.task is None and w.reshape_session is None
    assert shape(w.project['labels'][0]['geometry']).bounds==(20,20,30,34)


@pytest.fixture
def raster_image(tmp_path):
    import rasterio
    from rasterio.transform import Affine
    from geoforma.raster import inspect_source,make_recipe
    path=tmp_path/'source.tif'
    with rasterio.open(path,'w',driver='GTiff',width=100,height=100,count=3,dtype='uint8',crs='EPSG:3857',transform=Affine(2,.3,100,.2,-2,200)) as ds:ds.write(np.ones((3,100,100),np.uint8)*100)
    image=inspect_source(path);image['ready']=True;image['model_recipe']=make_recipe(image,[1,2,3]);image['display_recipe']=copy.deepcopy(image['model_recipe'])
    return image


def test_real_rotated_raster_uses_source_pixel_grid(raster_image):
    result=reshape_raster(raster_image,G,OUT)
    assert shape(result['geometry']).area==124 and result['window'][2]<100 and result['window'][3]<100


@pytest.fixture
def workbench(tmp_path,monkeypatch,raster_image):
    from PySide6.QtWidgets import QApplication
    from geoforma.window import MainWindow
    monkeypatch.setenv('GEOFORMA_DATA_DIR',str(tmp_path/'data'))
    app=QApplication.instance() or QApplication([]);w=MainWindow(auto_prepare=False);w.autosave=lambda:None
    w.project['images']=[raster_image];w.image=raster_image;w.view.set_image(100,100);w.render_timer.stop()
    label=dict(id='target',image_id=raster_image['id'],class_id=1,status='confirmed',annotation_mode='individual',geometry=G,points=[[25,25,1]],box=None,model={'backend':'sam'},window=[0,0,1024,1024])
    w.project['labels']=[label];w.selected_id='target';w.selected_ids={'target'};w.refresh_labels()
    yield w,app,tmp_path
    if w.reshape_session:w.cancel_reshape()
    w.image=None;w.dirty=False;w.close();app.processEvents()


def prepare_preview(w,stroke=OUT):
    if not w.selected_ids:w.select_label('target')
    w.begin_reshape();w.reshape_session['stroke']=copy.deepcopy(stroke)
    w.reshape_session['preview']=reshape_patch(reshape_intent(w.reshape_session['label']['geometry'],stroke),w.image)


def test_commit_lock_undo_redo_and_new_target_independence(workbench):
    w,app,tmp=workbench;original=copy.deepcopy(w.project['labels']);prepare_preview(w);w.commit_reshape();w.confirm()
    assert w.project['labels'][0]['editing_state']=='manual' and not w.model_prompts_locked()
    before=copy.deepcopy(w.project['labels']);w.select_label('target');w.edit_selected(locate=False);draft=copy.deepcopy(w.draft)
    calls=[];w.service.predict=lambda *args:calls.append(args)
    w.add_point(25,25,1);w.add_box([20,20,40,40]);w.clear_points();w.clear_box();w.reset_prior();w.predict()
    w.selected_points={0};w.delete_points();w.undo_prompt();w.redo_prompt()
    assert w.draft==draft and w.project['labels']==before and not calls
    assert not w.mode_actions['positive'].isEnabled() and not w.auto_apply.isEnabled()
    w.undo_context();assert w.project['labels']==original and not w.model_prompts_locked()
    w.redo_context();assert w.project['labels'][0]['editing_state']=='manual'
    w.select_label('target');w.edit_selected(locate=False);w.clear_draft();w.add_point(50,50,1)
    assert w.draft['points']==[[50,50,1]] and w.project['labels'][0]['editing_state']=='manual'


def test_manual_reshape_is_saved_beyond_earlier_prompt_box(workbench):
    import time
    w,app,tmp=workbench;w.project['labels'][0]['box']=[20,20,30,30]
    w.begin_reshape();w.reshape_session['stroke']=copy.deepcopy(OUT);w.finish_reshape()
    deadline=time.monotonic()+5
    while w.task and time.monotonic()<deadline:app.processEvents();time.sleep(.005)
    assert w.task is None and w.reshape_session is None
    w.confirm()
    saved=w.project['labels'][0]
    assert saved['editing_state']=='manual' and saved['box']==[20,20,30,30]
    assert shape(saved['geometry']).covers(Point(25.5,32.5))
    from geoforma.storage import save_project,load_project
    project_path=tmp/'manual-box.gfm';save_project(w.project,project_path)
    restored=load_project(project_path)['labels'][0]
    assert restored['editing_state']=='manual' and shape(restored['geometry']).covers(Point(25.5,32.5))


def test_repeated_manual_edits_need_all_undos_before_unlock(workbench):
    w,app,tmp=workbench;prepare_preview(w);w.commit_reshape();w.confirm()
    from test_smoothing import settled
    settled(w,app)
    # A second cut crosses the side not changed by the first edit.
    stroke=[[18,22],[22,22],[22,28],[18,28]];prepare_preview(w,stroke);w.commit_reshape();w.confirm()
    assert len(w.project['labels'][0]['manual_edits'])==2
    w.undo_context();w.select_label('target');w.edit_selected(locate=False);assert w.model_prompts_locked()
    w.undo_context();w.select_label('target');assert not w.model_prompts_locked()


def test_manual_class_save_and_model_changes_preserve_lock(workbench):
    w,app,tmp=workbench;prepare_preview(w);w.commit_reshape();w.confirm();w.select_label('target');w.edit_selected(locate=False)
    before=copy.deepcopy(w.draft);w.invalidate_model_drafts();assert w.draft==before
    w.confirm();assert w.project['labels'][0]['editing_state']=='manual' and w.project['labels'][0]['manual_edits']
    w.select_label('target');w.delete_selected();w.undo_label();w.select_label('target');w.edit_selected(locate=False);assert w.model_prompts_locked()


def test_manual_lock_and_undo_survive_project_reopen(workbench):
    w,app,tmp=workbench;original=copy.deepcopy(w.project['labels'][0]);prepare_preview(w);w.commit_reshape();w.confirm()
    w.project_path=tmp/'manual.gfm';w.save();w.open_project(w.project_path);w.select_label('target');w.edit_selected(locate=False)
    assert w.model_prompts_locked() and w.project['labels'][0]['editing_state']=='manual'
    w.undo_context();assert json.loads(json.dumps(w.project['labels'][0]))==json.loads(json.dumps(original))
    w.redo_context();assert w.project['labels'][0]['editing_state']=='manual'


def test_incomplete_stroke_recovers_and_cancel_does_not_change_label(workbench):
    w,app,tmp=workbench;original=copy.deepcopy(w.project['labels']);w.begin_reshape()
    w.add_reshape_point(22,28);w.add_reshape_point(22,34)
    stroke=copy.deepcopy(w.reshape_session['stroke']);w.project_path=tmp/'draft.gfm';w.save()
    w.cancel_reshape();w.open_project(w.project_path)
    assert w.reshape_session and w.reshape_session['stroke']==stroke and json.loads(json.dumps(w.project['labels']))==json.loads(json.dumps(original))
    w.cancel_reshape();assert json.loads(json.dumps(w.project['labels']))==json.loads(json.dumps(original))


def test_async_finish_saves_and_clears_stroke_without_running_sam(workbench):
    w,app,tmp=workbench;original=copy.deepcopy(w.project['labels']);w.begin_reshape();w.reshape_session['stroke']=copy.deepcopy(OUT)
    w.service.predict=lambda *args:pytest.fail('Reshape must not call SAM')
    w.finish_reshape();deadline=time.monotonic()+4
    while w.task and time.monotonic()<deadline:app.processEvents();time.sleep(.002)
    assert w.reshape_session is None and not w.view.reshape_items and not w.view.reshape_points
    assert w.project['labels']!=original and not w.draft
    assert shape(w.project['labels'][0]['geometry']).area==124
    item=w.view.overlay_records['target'];w.redraw();assert w.view.overlay_records['target'] is item


def test_service_rejects_manual_model_requests_before_loading():
    from geoforma.inference.engine import ModelEngine
    engine=ModelEngine();engine.prepare_backend=lambda *args:pytest.fail('Must reject before model load')
    for call in (engine.predict,engine.preview):
        with pytest.raises(ValueError,match='人工编辑'):call({}, {}, {'editing_state':'manual'},None)


def test_mouse_drawing_backspace_preview_and_save(workbench):
    from PySide6.QtCore import Qt,QPointF
    from PySide6.QtTest import QTest
    w,app,tmp=workbench;w.show();app.processEvents();w.view.fit_image();w.render_timer.stop()
    w.reshape_button.click();assert w.reshape_session and w.mode_settings.currentWidget() is w.prompt_group
    assert w.mode_actions['positive'].isEnabled()
    for x,y in OUT:
        p=w.view.mapFromScene(QPointF(x,y));QTest.mouseClick(w.view.viewport(),Qt.MouseButton.LeftButton,pos=p)
    assert len(w.reshape_session['stroke'])==4
    QTest.keyClick(w.view.viewport(),Qt.Key.Key_Backspace);assert len(w.reshape_session['stroke'])==3
    p=w.view.mapFromScene(QPointF(*OUT[-1]));QTest.mouseClick(w.view.viewport(),Qt.MouseButton.LeftButton,pos=p)
    original=copy.deepcopy(w.project['labels']);QTest.mouseClick(w.view.viewport(),Qt.MouseButton.RightButton,pos=p)
    deadline=time.monotonic()+4
    while w.task and time.monotonic()<deadline:app.processEvents();time.sleep(.002)
    assert w.reshape_session is None and not w.view.reshape_items and w.project['labels']!=original
    assert not w.confirm_button.isEnabled()
    assert w.project['labels'][0]['editing_state']=='manual'


def test_reshape_of_selected_label_preserves_another_label(workbench):
    w,app,tmp=workbench;original=copy.deepcopy(w.project['labels'][0])
    other=dict(copy.deepcopy(original),id='other',annotation_mode='individual')
    w.project['labels'].append(other);w.select_label('other')
    prepare_preview(w);w.commit_reshape();w.confirm()
    assert w.project['labels'][0]==original
    edited=next(l for l in w.project['labels'] if l['id']=='other');assert edited['editing_state']=='manual'
    w.select_label('target');assert not w.model_prompts_locked()
