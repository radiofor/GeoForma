"""A complete first frame, background reads, isolated sessions and load failures."""
import copy,threading,time
import pytest
from PySide6.QtCore import Qt,QTimer,QPoint
from PySide6.QtTest import QTest
from shapely.geometry import box,mapping,shape
from geoforma.domain import new_project
from geoforma.storage import save_project,load_project
from geoforma.project_loading import prepare_project
from geoforma.history import history_snapshot
from test_workbench import workbench
from test_reshape import raster_image


def wait_loading(w,app):
    deadline=time.monotonic()+8
    while w.loading_task or w.project_transition:
        app.processEvents();time.sleep(.002);assert time.monotonic()<deadline
    for _ in range(3):app.processEvents()


@pytest.fixture
def saved_project(tmp_path,raster_image):
    project=new_project();image=copy.deepcopy(raster_image);project['images']=[image]
    image['ready']=True
    geometry=mapping(box(20,20,40,40))
    project['labels']=[dict(id='saved',image_id=image['id'],status='confirmed',annotation_mode='individual',class_id=1,geometry=geometry)]
    project['workspace']={'image_id':image['id'],'operation':0,'annotation_mode':'individual','class_id':1,
                          'auto_apply':False,'view_window':[10,10,50,50]}
    path=tmp_path/'loaded.geoforma.json';save_project(project,path)
    return path,project


def test_preparation_is_side_effect_free_and_contains_first_frame_and_paths(saved_project):
    path,source=saved_project;before=copy.deepcopy(source)
    loaded=prepare_project(path,(800,600))
    assert loaded.frame is not None and loaded.window[2]<100
    confirmed,candidates=loaded.index.visible({})
    assert confirmed[0]['_render_path'].elementCount()>0 and not candidates
    assert source==before and all('_render_path' not in label for label in loaded.project['labels'])


def test_ui_open_preserves_old_frame_until_one_complete_commit(workbench,saved_project,monkeypatch):
    from geoforma.controllers import project_loading as workflow
    w,app,wait,errors=workbench;path,source=saved_project
    source['classes'].append({'id':2,'name':'Another class'})
    source['images'][0]['mode_sessions']={'individual':{'class_id':2,'draft':{}}}
    save_project(source,path)
    old=w.project;started=threading.Event();release=threading.Event();threads=[];ticks=[]
    original=workflow.prepare_project
    def slow(*args):
        threads.append(threading.get_ident());started.set()
        args[-1].signals.progress.emit(0,0,'缓存标签轮廓 · 256/512')
        while not release.wait(.003):args[-1].check()
        return original(*args)
    monkeypatch.setattr(workflow,'prepare_project',slow)
    sizes=[];set_image=w.view.set_image
    w.view.set_image=lambda x,y:(sizes.append((x,y)),set_image(x,y))[-1]
    signals=[];w.images.currentRowChanged.connect(lambda *_:signals.append('image'))
    w.classes.currentIndexChanged.connect(lambda *_:signals.append('class'))
    timer=QTimer();timer.setInterval(5);timer.timeout.connect(lambda:ticks.append(1));timer.start()
    assert w.request_project_open(path)
    assert w.project is old and w.project_transition.isVisible() and not sizes
    QTest.qWait(160);app.processEvents()
    assert started.is_set() and len(ticks)>5 and w.project is old
    assert w.project_transition.caption.isVisible()
    assert '缓存标签轮廓 · 256/512' in w.project_transition.caption.text()
    assert not w.request_project_open(path)
    QTest.keyClick(w.project_transition,Qt.Key.Key_N,Qt.KeyboardModifier.ControlModifier)
    assert w.project is old
    release.set();wait_loading(w,app);timer.stop()
    assert threads==[threads[0]] and threads[0]!=threading.get_ident()
    assert sizes==[(100,100)] and not signals and not errors
    assert w.view.base_item is not None or w.view.detail_item is not None
    assert 'saved' in w.view.overlay_records and not w.view.loading.isVisible()
    assert w.candidate_task is None and w.smoother.task is None


@pytest.mark.parametrize('recovering,name',[(False,'打开项目'),(True,'恢复工作')])
def test_named_loading_progress_remains_live_outside_snapshot_and_keeps_result(workbench,saved_project,monkeypatch,recovering,name):
    from geoforma.controllers import project_loading as workflow
    w,app,wait,errors=workbench;path,_=saved_project;old=w.project;release=threading.Event()
    original=workflow.prepare_project
    def slow(actual,size,task):
        task.signals.progress.emit(256,512,'缓存标签轮廓 · 256/512')
        while not release.wait(.003):task.check()
        return original(actual,size,task)
    monkeypatch.setattr(workflow,'prepare_project',slow)
    try:
        assert w.request_project_open(path,recover_latest=recovering)
        deadline=time.monotonic()+3
        while w.progress_count.text()!='轮廓 256 / 512':
            app.processEvents();QTest.qWait(2);assert time.monotonic()<deadline
        assert w.project is old and w.state_label.text()==name
        assert w.progress.maximum()==512 and w.progress.value()==256
        assert path.name in w.task_text.text() and '缓存标签轮廓' in w.task_text.text()
        assert w.cancel_button.isVisible() and w.cancel_button.isEnabled()
        assert w.project_transition.geometry().bottom()<w.statusBar().geometry().top()
        w.resize(1440,900);app.processEvents()
        assert w.project_transition.geometry().bottom()<w.statusBar().geometry().top()
        w.background_activity.delay=0;w.background_activity.set('autosave','自动保存','之前的项目');app.processEvents()
        assert w.state_label.text()==name and w.statusBar().text_slot.currentIndex()==0
        assert not w.run('不能同时启动计算',lambda task:None,lambda _:None,kind='interactive')
        from geoforma.tool_state import available_tools
        assert not any(available_tools(w).values())
        w.new();w.import_paths(['must_not_import.tif']);w.begin_reshape();w.set_tool('positive')
        assert w.project is old and w.task is None and w.reshape_session is None
        assert not w.project_actions['save'].isEnabled() and not w.import_button.isEnabled()
    finally:release.set()
    wait_loading(w,app);w.background_activity.set('autosave','');app.processEvents()
    assert w.progress.phase=='complete' and w.progress.value()==100 and w.progress.isVisible()
    assert w.state_label.text()==name and path.name in w.progress_panel.toolTip()
    assert not w.cancel_button.isVisible() and not w.progress_presentation.loading_active and not errors


@pytest.mark.parametrize('method',['button','escape'])
def test_cancel_project_loading_preserves_current_work_and_never_commits(workbench,saved_project,monkeypatch,method):
    from geoforma.controllers import project_loading as workflow
    w,app,wait,errors=workbench;path,_=saved_project;old=w.project;w.draft={'points':[[4,5,1]]}
    def slow(actual,size,task):
        task.signals.progress.emit(0,0,'加载全图预览…')
        while True:time.sleep(.003);task.check()
    monkeypatch.setattr(workflow,'prepare_project',slow)
    assert w.request_project_open(path)
    if method=='button':QTest.mouseClick(w.cancel_button,Qt.MouseButton.LeftButton)
    else:QTest.keyClick(w.project_transition,Qt.Key.Key_Escape)
    wait_loading(w,app)
    assert w.project is old and w.draft=={'points':[[4,5,1]]} and not errors
    assert w.progress.phase=='cancelled' and w.progress_result.text()=='已取消'
    assert w.progress.isVisible() and not w.progress_presentation.loading_active


def test_project_load_failure_keeps_named_failed_result(workbench,saved_project,tmp_path):
    w,app,wait,errors=workbench;path=tmp_path/'broken.geoforma.json';path.write_text('{',encoding='utf-8');old=w.project
    assert w.request_project_open(path,recover_latest=True);wait_loading(w,app)
    assert errors and w.project is old
    assert w.state_label.text()=='恢复工作' and w.progress.phase=='failed'
    assert w.progress_result.text()=='失败' and path.name in w.progress_panel.toolTip()


def test_completed_project_progress_yields_to_next_model_task(workbench,saved_project):
    w,app,wait,errors=workbench;path,_=saved_project
    assert w.request_project_open(path);wait_loading(w,app)
    assert w.state_label.text()=='打开项目' and w.progress.phase=='complete'
    release=threading.Event()
    def model(task):
        task.signals.progress.emit(0,0,'加载 SAM 模型…');assert release.wait(5)
    try:
        assert w.run('准备模型',model,lambda _:None,kind='model_warmup')
        deadline=time.monotonic()+3
        while w.task_stage!='加载 SAM 模型…':
            app.processEvents();QTest.qWait(2);assert time.monotonic()<deadline
        assert w.state_label.text()=='加载模型' and w.progress.phase=='running'
        assert '打开项目' not in w.progress_panel.toolTip()
    finally:release.set()
    wait();assert w.progress.phase=='complete' and w.state_label.text()=='加载模型' and not errors


def test_read_or_raster_failure_keeps_existing_work(workbench,saved_project,tmp_path):
    w,app,wait,errors=workbench;path,source=saved_project
    original=w.project;w.draft={'points':[[10,10,1]]};before=copy.deepcopy(w.draft)
    malformed=tmp_path/'invalid.geoforma.json';malformed.write_text('{',encoding='utf-8')
    assert w.request_project_open(malformed);wait_loading(w,app)
    assert errors and w.project is original and w.draft==before and w.project_transition is None
    errors.clear();missing=copy.deepcopy(source);missing['images'][0]['path']=str(tmp_path/'missing.tif')
    save_project(missing,malformed);assert w.request_project_open(malformed);wait_loading(w,app)
    assert errors and w.project is original and w.draft==before


def test_shrinking_sidebar_is_fully_laid_out_before_transition_capture(workbench,saved_project,tmp_path,monkeypatch):
    w,app,wait,errors=workbench;path,source=saved_project;w.resize(1440,1400)
    many=copy.deepcopy(source);many['images']=[dict(copy.deepcopy(source['images'][0]),id=f'image-{i}') for i in range(6)]
    many['labels']=[];many['workspace']={};large=tmp_path/'many.geoforma.json';save_project(many,large)
    assert w.open_project(large);app.processEvents();assert w.images.height()>100
    observed=[];finish=w.finish_project_transition
    def check(committed):
        if committed:
            bottom=w.images.mapTo(w,QPoint()).y()+w.images.height()
            observed.append(w.image_info.mapTo(w,QPoint()).y()-bottom)
        finish(committed)
    monkeypatch.setattr(w,'finish_project_transition',check)
    assert w.request_project_open(path);wait_loading(w,app)
    assert observed==[6] and not errors


def test_smoothing_and_draft_ready_before_transition_finishes(workbench,saved_project,monkeypatch):
    w,app,wait,errors=workbench;path,source=saved_project
    source['smoothing']={'individual':{'enabled':True,'value':1.}}
    source['workspace']['draft']={'geometry':mapping(box(55,55,75,75)),'points':[[60,60,1]],'pending':False}
    save_project(source,path);observed=[];original=w.finish_project_transition
    def finish(committed):
        if committed:
            observed.append((w.view.base_item is not None or w.view.detail_item is not None,
                             set(w.view.overlay_records),w.smoother.task,w.smoother.timer.isActive(),w.smooth_enabled.isChecked()))
        original(committed)
    monkeypatch.setattr(w,'finish_project_transition',finish)
    assert w.request_project_open(path);wait_loading(w,app)
    assert observed==[(True,{'saved','__draft'},None,False,True)]
    assert not shape(w.view.overlay_records['__draft'].geometry_value).equals(shape(w.draft['geometry']))
    assert not errors


def test_hidden_reshape_stroke_restores_and_becomes_visible_when_raw_view_ends(workbench,saved_project):
    w,app,wait,errors=workbench;path,source=saved_project
    source['workspace'].update(raw_view=True,reshape={'label_id':'saved','target':'label','stroke':[[20,22],[19,30],[20,38]],'alternate':False})
    save_project(source,path);assert w.request_project_open(path);wait_loading(w,app)
    assert not w.raw_view_action.isChecked() and w.reshape_session['stroke']==[[20,22],[19,30],[20,38]]
    assert not w.visibility_toolbar.widgetForAction(w.raw_view_action).isChecked()
    assert w.visibility_toolbar.widgetForAction(w.raw_view_action).property('visibilityState')=='hidden'
    assert w.view.reshape_items and not any(item.isVisible() for item in w.view.reshape_items)
    w.raw_view_action.setChecked(True);w.toggle_raw()
    assert all(item.isVisible() for item in w.view.reshape_items) and not errors
    w.cancel_reshape()


def test_restore_does_not_overwrite_other_mode_sessions_or_run_inference(workbench,saved_project):
    w,app,wait,errors=workbench;path,source=saved_project;image=source['images'][0]
    source['labels'].append(dict(id='candidate',image_id=image['id'],status='candidate',annotation_mode='automatic',class_id=None,
                                  geometry=mapping(box(50,50,80,80)),window=[0,0,100,100]))
    source['workspace'].update(operation=1,annotation_mode='automatic',draft={'base_id':'candidate','geometry':source['labels'][1]['geometry']})
    image['mode_sessions']={'individual':{'draft':{'points':[[10,10,1]],'pending':False},'selected_ids':['saved'],'undo':[{'points':[]}],'redo':[]},
                            'automatic':{'draft':{},'selected_ids':['candidate'],'undo':[],'redo':[]}}
    source['history']={'schema':1,'labels':{'individual':{'undo':[[['saved',None,0]]],'redo':[]},'automatic':{'undo':[[['candidate',None,1]]],'redo':[]}}}
    save_project(source,path);expected=load_project(path);calls=[];w.service.predict=lambda *args:calls.append(args)
    assert w.request_project_open(path);wait_loading(w,app)
    assert w.mode_index==0 and w.draft['points']==[[10,10,1]]
    assert w.project['images'][0]['mode_sessions']['individual']==expected['images'][0]['mode_sessions']['individual']
    assert {label['id'] for label in w.current_labels()}=={'saved','candidate'} and not calls
    assert w.draft['points']==[[10,10,1]] and w.prompt_undo==[{'points':[]}]
    assert w.label_undo==history_snapshot(expected['history'])['labels']['individual']['undo'] and not errors


def test_navigation_scale_and_center_do_not_drift_across_repeated_loads(workbench,saved_project):
    w,app,wait,errors=workbench;path,source=saved_project
    source['workspace']['navigation']={'scale':12.,'center':[45.,50.]};save_project(source,path)
    assert w.open_project(path);app.processEvents();first=w.view.capture_navigation()
    for _ in range(3):
        w.capture_workspace();save_project(w.project,path);assert w.open_project(path);app.processEvents()
        state=w.view.capture_navigation()
        assert state['scale']==first['scale']
        assert max(abs(a-b) for a,b in zip(state['center'],first['center']))<1e-7
    assert not errors


def test_close_cancels_background_open_without_replacing_work(workbench,saved_project,monkeypatch):
    from geoforma.controllers import project_loading as workflow
    w,app,wait,errors=workbench;path,_=saved_project;original=w.project;started=threading.Event()
    def slow(*args):
        started.set()
        while True:time.sleep(.003);args[-1].check()
    monkeypatch.setattr(workflow,'prepare_project',slow)
    assert w.request_project_open(path)
    deadline=time.monotonic()+3
    while not started.is_set():app.processEvents();time.sleep(.002);assert time.monotonic()<deadline
    w.close();wait_loading(w,app)
    deadline=time.monotonic()+3
    while not w.shutdown_complete:app.processEvents();time.sleep(.002);assert time.monotonic()<deadline
    assert w.project is original and not w.isVisible() and not errors


@pytest.mark.parametrize('navigation',[{'scale':0,'center':[0,0]},{'scale':1,'center':['invalid',0]},'invalid'])
def test_invalid_navigation_rejected_before_live_state_changes(workbench,saved_project,navigation):
    w,app,wait,errors=workbench;path,source=saved_project;original=w.project
    source['workspace']['navigation']=navigation;save_project(source,path)
    assert not w.open_project(path) and w.project is original and errors
