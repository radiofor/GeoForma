import copy,json,time
from types import SimpleNamespace
import numpy as np
import pytest
from shapely.geometry import shape,mapping,box
from geoforma.domain import new_project
from geoforma.storage import load_project,save_project
from geoforma.reshape import reshape_intent,reshape_patch
from test_reshape import workbench,raster_image,OUT,G,prepare_preview


@pytest.mark.parametrize('commit',[False,True])
def test_exit_reshape_restores_table_navigation_and_save(workbench,commit):
    w,app,tmp=workbench;prepare_preview(w)
    assert w.labels_table.isEnabled() and w.mode_actions['pan'].isEnabled()
    if commit:w.commit_reshape()
    else:w.cancel_reshape()
    assert w.labels_table.isEnabled() and w.mode_actions['pan'].isEnabled() and w.mode_actions['select'].isEnabled()
    assert w.project_actions['save'].isEnabled() and w.reshape_button.isVisible()==w.isVisible()


def test_raw_view_hides_stroke_and_prevents_drawing(workbench):
    w,app,tmp=workbench;w.begin_reshape();w.add_reshape_point(22,28)
    w.raw_view_action.setChecked(False);w.toggle_raw();before=copy.deepcopy(w.reshape_session['stroke'])
    assert all(not item.isVisible() for item in w.view.reshape_items) and not w.view.reshape_enabled
    w.add_reshape_point(22,34);assert w.reshape_session['stroke']==before
    w.raw_view_action.setChecked(True);w.toggle_raw();assert all(item.isVisible() for item in w.view.reshape_items)


@pytest.mark.parametrize('stroke',[[[float('nan'),1],[2,3]],[[float('inf'),1],[2,3]],[[1,2,3],[4,5,6]],[[1,2]],'not a line'])
def test_invalid_strokes_fail_cleanly(stroke):
    with pytest.raises(ValueError):reshape_intent(G,stroke)


@pytest.mark.parametrize('damage',['ids','geometry','manual_state','annotation_mode','manual_edits','model','classes','stroke','history'])
def test_invalid_project_is_rejected_without_changing_workspace(workbench,damage):
    w,app,tmp=workbench;project=copy.deepcopy(w.project)
    if damage=='ids':project['labels'].append(copy.deepcopy(project['labels'][0]))
    elif damage=='geometry':project['labels'][0]['geometry']={'type':'Point','coordinates':[1,2]}
    elif damage=='manual_state':project['labels'][0]['editing_state']='unknown'
    elif damage=='annotation_mode':project['labels'][0]['annotation_mode']='unknown'
    elif damage=='manual_edits':project['labels'][0]['manual_edits']={'invalid':True}
    elif damage=='model':project['model']={}
    elif damage=='classes':project['classes'].append(copy.deepcopy(project['classes'][0]))
    elif damage=='stroke':project['workspace']={'reshape':{'label_id':'target','stroke':[[float('nan'),2]]}}
    else:
        old=copy.deepcopy(project['labels'][0]);old['geometry']={'type':'Point','coordinates':[1,2]}
        project['history']={'schema':1,'labels':{'individual':{'undo':[[['target',old,0]]],'redo':[]}}}
    path=tmp/'bad.gfm';path.write_text(json.dumps(project),encoding='utf-8')
    with pytest.raises(ValueError):load_project(path)
    original=w.project;sessions=copy.deepcopy(w.image_sessions);errors=[];w.error=errors.append;w.open_project(path)
    assert errors and w.project is original and w.image_sessions==sessions


def test_adjacent_label_is_not_eroded_by_occupied_mask():
    result=reshape_patch(reshape_intent(G,OUT),{'width':100,'height':100},blockers=[mapping(box(28,30,30,34))])
    assert result['added_pixels']==24 and shape(result['geometry']).area==124


def test_cancel_check_reaches_polygon_extraction():
    from geoforma.tasks import Cancelled
    count=[0]
    def check():
        count[0]+=1
        if count[0]>=2:raise Cancelled()
    with pytest.raises(Cancelled):reshape_patch(reshape_intent(G,OUT),{'width':100,'height':100},task=SimpleNamespace(check=check))


def test_generated_staircase_edits_keep_grid_and_unchanged_lower_body():
    rng=np.random.default_rng(42)
    for _ in range(80):
        x=float(rng.uniform(22,25));height=float(rng.uniform(31.2,36.7))
        stroke=[[21,28],[x,height],[29,28]]
        try:result=reshape_patch(reshape_intent(G,stroke),{'width':100,'height':100})
        except ValueError as error:
            assert '改变' in str(error);continue
        g=shape(result['geometry']);assert g.is_valid and g.intersection(box(0,0,100,29)).equals(shape(G).intersection(box(0,0,100,29)))
        assert all(x==int(x) and y==int(y) for x,y in g.exterior.coords)


def test_bootstrap_disables_embedded_python_in_vrt(monkeypatch):
    monkeypatch.setenv('GDAL_VRT_ENABLE_PYTHON','YES')
    from main import configure_runtime
    configure_runtime()
    import os
    assert os.environ['GDAL_VRT_ENABLE_PYTHON']=='NO'


def test_canvas_loading_feedback_disappears_when_raster_arrives(workbench):
    w,app,tmp=workbench;w.view.set_image(100,100);assert not w.view.loading.isHidden()
    w.view.show_raster_error();assert '失败' in w.view.loading.text()
    w.view.show_raster(np.ones((10,10,3),np.uint8),np.ones((10,10),bool),[0,0,100,100]);assert w.view.loading.isHidden()
    w.view.set_image(0,0);assert w.view.loading.isHidden()
