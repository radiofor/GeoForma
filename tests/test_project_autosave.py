"""Named projects persist edits automatically, including queued transitions."""
import threading,time
from pathlib import Path
import pytest
from PySide6.QtWidgets import QApplication,QFileDialog
from shapely.geometry import box,mapping
from geoforma.window import MainWindow
from geoforma.storage import load_project,save_project
from geoforma.project_save_queue import ProjectSaveQueue,ProjectSaveRequest
from test_reshape import raster_image


def until(app,predicate):
    deadline=time.monotonic()+8
    while not predicate():
        app.processEvents();time.sleep(.003)
        assert time.monotonic()<deadline,'Project save did not settle'
    app.processEvents()


@pytest.fixture
def automatic_project(tmp_path,monkeypatch):
    monkeypatch.setenv('GEOFORMA_DATA_DIR',str(tmp_path/'data'))
    monkeypatch.setenv('GEOFORMA_SETTINGS_FILE',str(tmp_path/'settings.ini'))
    app=QApplication.instance() or QApplication([]);w=MainWindow(auto_prepare=False)
    w.request_render=lambda *args:None;w.autosave_timer.stop();w.error=lambda text:None
    w.show();app.processEvents();w.render_timer.stop()
    yield w,app,tmp_path
    w.autosave_debounce.stop()
    until(app,lambda:w.autosave_task is None)
    w.project_saves.pending.clear();w.project_saves.failed.clear()
    w.image=None;w.dirty=False;w.close();app.processEvents()


def first_save(w,tmp,monkeypatch):
    path=tmp/'automatic.gfm'
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *args:(str(path),''))
    assert w.project_actions['save'].isEnabled()
    w.project_actions['save'].trigger()
    assert w.project_path==path and path.is_file() and not w.project_actions['save'].isEnabled()
    return path


def test_project_directory_button_tracks_saved_project(automatic_project,monkeypatch):
    from PySide6.QtGui import QDesktopServices
    w,app,tmp=automatic_project
    assert not w.project_directory_button.isEnabled()
    opened=[]
    monkeypatch.setattr(QDesktopServices,'openUrl',lambda url:opened.append(url.toLocalFile()) or True)
    first_save(w,tmp,monkeypatch)
    assert w.project_directory_button.isEnabled()
    w.project_directory_button.click()
    assert Path(opened[0])==tmp.resolve()


def test_first_save_removes_only_its_untitled_recovery(automatic_project,monkeypatch,raster_image):
    w,app,tmp=automatic_project;w.project['images']=[raster_image];w.mark_dirty();w.autosave()
    until(app,lambda:not w.dirty and w.autosave_task is None)
    recovery=tmp/'data'/'recovery'/'untitled.gfm';assert recovery.is_file()
    path=first_save(w,tmp,monkeypatch)
    assert path.is_file() and not recovery.exists()
    assert not Path(str(path)+'.bak').exists() and not Path(str(path)+'.autosave').exists()


def saved(w,app):
    until(app,lambda:not w.dirty and w.autosave_task is None and not w.project_saves.pending)


def test_autosave_succeeds_silently_without_replacing_other_messages(automatic_project,monkeypatch):
    w,app,tmp=automatic_project;path=first_save(w,tmp,monkeypatch)
    w.statusBar().showMessage('其他操作的消息')
    w.project['classes'][0]['name']='保存后的类别';w.mark_dirty();w.autosave()
    assert 'autosave' not in w.background_activity.entries
    saved(w,app)
    assert w.statusBar().currentMessage()=='其他操作的消息'
    assert load_project(path)['classes'][0]['name']=='保存后的类别'


def test_autosave_unavailable_resource_directory_shows_failure(automatic_project,monkeypatch,raster_image):
    w,app,_=automatic_project
    def unavailable():raise OSError('unavailable')
    monkeypatch.setattr('geoforma.resource_location.current_resource_dir',unavailable)
    w.project['images']=[raster_image];w.mark_dirty()
    assert w.autosave() is False
    assert '自动保存未完成' in w.statusBar()._error_toast.label.text()
    assert w.dirty and w.autosave_task is None


def test_close_with_blocked_migration_reports_error_without_losing_work(automatic_project,monkeypatch,raster_image):
    w,app,_=automatic_project;w.project['images']=[raster_image];w.mark_dirty()
    monkeypatch.setattr('geoforma.resource_migration.pending_migration',lambda:True)
    assert not w.close() and w.isVisible() and w.dirty and not w.closing
    assert '资源迁移未完成' in w.statusBar()._error_toast.label.text()


def block_first_write(monkeypatch):
    started=threading.Event();release=threading.Event();written=[]
    def write(project,path,**kwargs):
        if not started.is_set():
            started.set();assert release.wait(5)
        written.append((project['classes'][0]['name'],Path(path)));save_project(project,path,**kwargs)
    monkeypatch.setattr('geoforma.controllers.projects.save_project',write)
    return started,release,written


def test_first_save_disables_action_and_later_edits_update_formal_file(automatic_project,monkeypatch):
    w,app,tmp=automatic_project;path=first_save(w,tmp,monkeypatch)
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *args:pytest.fail('Named project asked for a path'))
    w.project['classes'][0]['name']='自动保存的类别';w.mark_dirty();w.update_controls()
    assert not w.project_actions['save'].isEnabled()
    w.project_actions['save'].trigger();saved(w,app)
    assert load_project(path)['classes'][0]['name']=='自动保存的类别'
    assert not Path(str(path)+'.autosave').exists()
    assert not Path(str(path)+'.bak').exists()
    assert w.settings.value('recovery/last_work')==str(path)


def test_cancelled_first_save_keeps_action_available(automatic_project,monkeypatch):
    w,app,tmp=automatic_project
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *args:('',''))
    w.project_actions['save'].trigger()
    assert w.project_path is None and w.project_actions['save'].isEnabled()


def test_project_save_and_open_permission_errors_use_readable_toast(automatic_project,monkeypatch):
    w,app,tmp=automatic_project
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *args:(str(tmp/'denied.gfm'),''))
    def denied(*args,**kwargs):raise PermissionError(13,'Access denied')
    monkeypatch.setattr('geoforma.controllers.projects.save_project',denied)
    w.save();assert '项目保存失败：没有访问权限' in w.statusBar()._error_toast.label.text()
    assert 'PermissionError' in w.log.toPlainText() and w.project_path is None
    monkeypatch.setattr('geoforma.storage.load_project',denied)
    assert not w.open_project(tmp/'denied.gfm')
    assert w.statusBar()._error_toast.pending
    w.statusBar()._error_toast._advance()
    assert '打开项目失败：没有访问权限' in w.statusBar()._error_toast.label.text()


def test_moved_project_is_not_recreated_by_autosave(automatic_project,monkeypatch):
    w,app,tmp=automatic_project;path=first_save(w,tmp,monkeypatch)
    moved=tmp/'moved.gfm';path.rename(moved)
    w.project['classes'][0]['name']='等待保存';w.mark_dirty();w.autosave()
    until(app,lambda:w.autosave_task is None)
    assert not path.exists() and w.dirty and w.project_saves.failed
    bar=w.statusBar();assert '项目文件不存在或已移动' in bar._error_toast.label.text()
    bar.showMessage('其他操作完成',5);bar.set_task_active(True)
    assert '项目文件不存在或已移动' in bar._error_toast.label.text()
    bar.clearMessage();bar.set_task_active(False)
    assert load_project(moved)['classes'][0]['name']=='类别 1'
    moved.rename(path);w.autosave();saved(w,app)
    assert not bar._error_toast.label.isVisible()
    assert load_project(path)['classes'][0]['name']=='等待保存'


@pytest.mark.parametrize('old_fails',[False,True])
def test_old_project_save_completion_cannot_replace_new_project_error(automatic_project,monkeypatch,old_fails):
    w,app,tmp=automatic_project;path=first_save(w,tmp,monkeypatch)
    started=threading.Event();release=threading.Event()
    def delayed(project,target,**kwargs):
        started.set();assert release.wait(5)
        if old_fails:raise OSError('旧项目保存失败')
        save_project(project,target,**kwargs)
    monkeypatch.setattr('geoforma.controllers.projects.save_project',delayed)
    try:
        w.project['classes'][0]['name']='等待写入';w.mark_dirty();w.autosave();until(app,started.is_set)
        old_epoch=w.project_epoch;w.new();assert w.project_epoch!=old_epoch
        key=('autosave',w.project_epoch,'unavailable');w.report_autosave_problem(key,'新项目无法保存')
        release.set();until(app,lambda:w.autosave_task is None and not w.project_saves.pending)
        assert w.statusBar()._error_toast.label.text()=='新项目无法保存'
        assert ('autosave',old_epoch,'unavailable') not in w._autosave_problems
    finally:release.set()


def test_repeated_autosave_failure_reports_once_until_recovery(automatic_project,monkeypatch):
    w,app,tmp=automatic_project;path=first_save(w,tmp,monkeypatch)
    moved=tmp/'moved.gfm';path.rename(moved);shown=[]
    bar=w.statusBar();original=bar.report_error
    def report(message,source=None):shown.append(message);original(message,source=source)
    monkeypatch.setattr(bar,'report_error',report)
    w.mark_dirty();w.autosave();until(app,lambda:w.autosave_task is None)
    w.autosave();until(app,lambda:w.autosave_task is None)
    assert len(shown)==1 and '项目文件不存在或已移动' in shown[0]
    moved.rename(path);w.autosave();saved(w,app)
    path.rename(moved);w.mark_dirty();w.autosave();until(app,lambda:w.autosave_task is None)
    assert len(shown)==2
    moved.rename(path);w.autosave();saved(w,app)


def test_autosave_overwrites_external_edits_with_current_project(automatic_project,monkeypatch):
    w,app,tmp=automatic_project;path=first_save(w,tmp,monkeypatch)
    external=load_project(path);external['classes'][0]['name']='外部修改'
    save_project(external,path)
    w.project['classes'][0]['name']='软件中的内容';w.mark_dirty();w.autosave();saved(w,app)
    assert load_project(path)['classes'][0]['name']=='软件中的内容'
    assert not Path(str(path)+'.autosave').exists() and not Path(str(path)+'.bak').exists()


def test_old_recovery_sidecar_is_not_opened(automatic_project,monkeypatch):
    w,app,tmp=automatic_project;path=first_save(w,tmp,monkeypatch)
    Path(str(path)+'.autosave').write_bytes(path.read_bytes())
    w.project['classes'][0]['name']='当前编辑';w.mark_dirty()
    assert w.request_project_open(path,recover_latest=True)
    until(app,lambda:w.loading_task is None and w.project_transition is None)
    assert w.project['classes'][0]['name']=='当前编辑'


def test_save_edit_class_delete_and_undo_all_reach_formal_file(automatic_project,monkeypatch,raster_image):
    w,app,tmp=automatic_project;path=first_save(w,tmp,monkeypatch)
    w.project['images']=[raster_image];w.image=raster_image;w.view.set_image(100,100)
    w.project['classes'].append({'id':2,'name':'第二类别'});w.refresh_classes()
    w.draft={'geometry':mapping(box(10,10,20,20)),'points':[],'box':None,'pending':False}
    w.confirm();saved(w,app);identifier=w.project['labels'][0]['id']
    assert len(load_project(path)['labels'])==1
    w.change_label_class(identifier,2);saved(w,app)
    assert load_project(path)['labels'][0]['class_id']==2
    w.select_label(identifier);w.delete_selected();saved(w,app)
    assert not load_project(path)['labels']
    w.undo_context();saved(w,app)
    assert load_project(path)['labels'][0]['id']==identifier


def test_edits_during_write_are_coalesced_without_losing_latest_state(automatic_project,monkeypatch):
    w,app,tmp=automatic_project;path=first_save(w,tmp,monkeypatch)
    started,release,written=block_first_write(monkeypatch)
    try:
        w.project['classes'][0]['name']='第一次';w.mark_dirty();w.autosave();until(app,started.is_set)
        for name in ('中间状态','最后状态'):
            w.project['classes'][0]['name']=name;w.mark_dirty();w.autosave()
        assert len(w.project_saves.pending)==1
        release.set();saved(w,app)
        assert load_project(path)['classes'][0]['name']=='最后状态'
        assert not any(name=='中间状态' for name,_ in written)
    finally:release.set()


def test_new_project_keeps_old_pending_snapshot_and_reenables_save(automatic_project,monkeypatch):
    w,app,tmp=automatic_project;path=first_save(w,tmp,monkeypatch)
    started,release,_=block_first_write(monkeypatch)
    try:
        w.project['classes'][0]['name']='开始写入';w.mark_dirty();w.autosave();until(app,started.is_set)
        w.project['classes'][0]['name']='切换前的最新内容';w.mark_dirty();w.new()
        assert w.project_path is None and w.project_actions['save'].isEnabled()
        release.set();until(app,lambda:w.autosave_task is None and not w.project_saves.pending)
        assert load_project(path)['classes'][0]['name']=='切换前的最新内容'
        assert w.project['classes'][0]['name']=='类别 1'
    finally:release.set()


def test_failure_keeps_dirty_recovery_and_retries_without_save_button(automatic_project,monkeypatch):
    w,app,tmp=automatic_project;path=first_save(w,tmp,monkeypatch);fail=True
    def write(project,target,**kwargs):
        if fail and Path(target)==path:raise OSError('disk unavailable')
        save_project(project,target,**kwargs)
    monkeypatch.setattr('geoforma.controllers.projects.save_project',write)
    w.project['classes'][0]['name']='需要重试的内容';w.mark_dirty();w.autosave()
    until(app,lambda:w.autosave_task is None)
    assert w.dirty and w.project_saves.failed and not w.project_actions['save'].isEnabled()
    assert load_project(path)['classes'][0]['name']=='类别 1'
    assert not Path(str(path)+'.autosave').exists()
    fail=False;w.autosave();saved(w,app)
    assert load_project(path)['classes'][0]['name']=='需要重试的内容'


def test_opening_same_project_waits_for_queued_edits(automatic_project,monkeypatch):
    w,app,tmp=automatic_project;path=first_save(w,tmp,monkeypatch)
    started,release,_=block_first_write(monkeypatch)
    try:
        w.project['classes'][0]['name']='写入中';w.mark_dirty();w.autosave();until(app,started.is_set)
        w.project['classes'][0]['name']='读取前必须保存的新内容';w.mark_dirty()
        assert w.request_project_open(path,recover_latest=True)
        release.set();until(app,lambda:w.loading_task is None and w.project_transition is None)
        assert w.project['classes'][0]['name']=='读取前必须保存的新内容'
        assert load_project(path)['classes'][0]['name']=='读取前必须保存的新内容'
        assert not w.project_actions['save'].isEnabled()
    finally:release.set()


def test_queue_order_ignores_wall_clock_and_discards_old_failed_writes(tmp_path):
    queue=ProjectSaveQueue();path=tmp_path/'project.gfm'
    old=ProjectSaveRequest({'_snapshot_time_ns':100},Path(str(path)+'.autosave'),path,0,1,'old',queue.next_order())
    newer=ProjectSaveRequest({'_snapshot_time_ns':50},Path(str(path)+'.autosave'),path,0,2,'new',queue.next_order())
    queue.saved(path,old.order);queue.submit(newer)
    assert queue.pop() is newer
    assert queue.busy  # Taking a request must not let project loading race its write.
    queue.saved(path,newer.order);queue.complete();queue.defer(old)
    assert not queue.failed and not queue.busy
