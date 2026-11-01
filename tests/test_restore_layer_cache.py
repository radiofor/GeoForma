import copy
from PySide6.QtCore import QRectF
from shapely.geometry import box,mapping
from geoforma.storage import save_project
from test_workbench import workbench
from test_reshape import raster_image
from test_project_loading import saved_project


def test_zoomed_restore_prepares_full_raster_and_all_annotation_items(workbench,saved_project,monkeypatch):
    w,app,wait,errors=workbench;path,project=saved_project;image=project['images'][0]
    project['labels']=[dict(id=str(i),image_id=image['id'],status='confirmed',annotation_mode='individual',class_id=1,
                            geometry=mapping(box(5+i*10,5+j*20,9+i*10,9+j*20))) for j in range(4) for i in range(9)]
    # Give every saved record a unique identity.
    for i,label in enumerate(project['labels']):label['id']=str(i)
    project['workspace']['navigation']={'scale':40.,'center':[10.,10.]}
    save_project(project,path);assert w.open_project(path);app.processEvents()
    assert w.view.layers.base_item is not None and w.view.layers.detail_item is not None
    items=dict(w.view.overlay_records)
    assert len(items)==36 and w.labels_table.rowCount()==36
    def unexpected(*args):raise AssertionError('Zoom must reuse the prepared label paths')
    monkeypatch.setattr(w.view.layers,'cached_path',unexpected)
    for rect in (QRectF(0,0,100,100),QRectF(70,60,10,10),QRectF(0,0,100,100)):
        w.view.fitInView(rect);w.redraw();app.processEvents()
        assert all(w.view.overlay_records[key] is item for key,item in items.items())
        assert w.labels_table.rowCount()==36
    assert not errors


def test_table_keeps_saved_records_hidden_by_other_labels_or_current_draft(workbench,saved_project):
    w,app,wait,errors=workbench;path,project=saved_project;label=project['labels'][0]
    project['smoothing']['individual']['enabled']=False  # Legacy overlapping labels are inspected without smoothing.
    project['labels']=[dict(label,id='covered'),dict(label,id='covering')]
    save_project(project,path);assert w.open_project(path)
    assert w.labels_table.rowCount()==2
    w.select_label('covering');w.edit_selected(locate=False)
    assert w.labels_table.rowCount()==2
    assert {w.labels_table.item(row,0).data(256) for row in range(2)}=={'covered','covering'}
    assert not errors


def test_selected_saved_manual_label_does_not_lock_new_target_tools(workbench,saved_project):
    w,app,wait,errors=workbench;path,project=saved_project
    from geoforma.domain import data_dir
    w.service.activate_project(data_dir(),project['cache_id'])
    project['images'][0]['prepared_cache_revision']=w.service.cache_revision
    project['labels'][0]['editing_state']='manual';save_project(project,path);assert w.open_project(path)
    w.auto_apply.setChecked(False);w.select_label('saved');before=copy.deepcopy(w.project['labels'])
    assert not w.draft and not w.model_prompts_locked() and w.confirm_button.text()=='已保存'
    for mode in ('positive','negative','box'):
        assert w.mode_actions[mode].isEnabled();w.set_tool(mode);assert w.view.mode==mode
    w.set_tool('positive');w.add_point(60,60,1)
    assert not w.draft.get('base_id') and w.draft['points']==[[60,60,1]]
    assert w.project['labels']==before
    w.clear_draft();w.select_label('saved');w.edit_selected(locate=False)
    assert w.model_prompts_locked() and not w.mode_actions['positive'].isEnabled()
    assert w.confirm_button.isEnabled()
    w.confirm();assert w.project['labels'][0]['editing_state']=='manual' and not errors


def test_restored_draft_does_not_automatically_select_its_base(workbench,saved_project):
    w,app,wait,errors=workbench;path,project=saved_project
    label=project['labels'][0]
    project['workspace']['draft']={'base_id':'saved','geometry':label['geometry'],'pending':False}
    save_project(project,path);assert w.open_project(path)
    assert w.draft['base_id']=='saved' and not w.selected_ids and not w.labels_table.selectedItems()
    assert w.confirm_button.isEnabled() and not errors
