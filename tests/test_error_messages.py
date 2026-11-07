"""Error summaries retain actionable domain text without exposing tracebacks."""
import pytest
from geoforma.error_messages import user_message,operation_error
from test_workbench import workbench


@pytest.mark.parametrize(('diagnostic','expected'),[
    ('Traceback (most recent call last):\n  File "internal.py", line 8\nPermissionError: [WinError 5] 拒绝访问。', '没有访问权限，请检查文件或目录权限。'),
    ('FileNotFoundError: [Errno 2] No such file or directory: x', '文件或目录不存在，请检查路径或重新选择。'),
    ('TimeoutError: timed out', '操作超时，请稍后重试。'),
    ('ConnectionResetError: connection reset', '连接失败，请检查网络后重试。'),
    ('OSError: [WinError 112] There is not enough space on the disk', '磁盘空间不足，请释放空间后重试。'),
    ('OSError: [WinError 32] process cannot access file', '文件正被其他程序占用，请关闭相关程序后重试。'),
    ('OSError: [WinError 13] The data is invalid', '文件数据无效，请检查文件后重试。'),
    ('RuntimeError: 项目文件不存在或已移动，自动保存已暂停；请先将项目文件移回原位置。', '项目文件不存在或已移动，自动保存已暂停；请先将项目文件移回原位置。'),
    ('FileNotFoundError: 缺少模型文件，请重新选择权重。', '缺少模型文件，请重新选择权重。'),
    ('FileNotFoundError: [Errno 2] 缺少模型文件，请重新选择权重。', '缺少模型文件，请重新选择权重。'),
    ('ValueError: 编辑线无效，请调整编辑线。', '编辑线无效，请调整编辑线。'),
    ('', '操作未完成，请重试。'),
])
def test_user_message(diagnostic,expected):
    assert user_message(diagnostic)==expected


def test_user_message_accepts_exception_objects():
    assert user_message(PermissionError(13,'Access denied'))=='没有访问权限，请检查文件或目录权限。'
    assert user_message(OSError('[WinError 112] There is not enough space'))=='磁盘空间不足，请释放空间后重试。'
    assert user_message(ValueError('请输入有效类别。'))=='请输入有效类别。'


def test_task_error_reports_summary_and_keeps_original_log(workbench):
    from geoforma.controllers.tasks import TaskWorkflow
    w,app,wait,errors=workbench
    diagnostic='Traceback (most recent call last):\n  File "worker.py", line 8\nPermissionError: [WinError 5] 拒绝访问。'
    TaskWorkflow.error(w,diagnostic)
    assert w.statusBar()._error_toast.label.text()=='没有访问权限，请检查文件或目录权限。'
    assert diagnostic in w.log.toPlainText()


@pytest.mark.parametrize(('kind','reason','expected'),[
    ('import','文件或目录不存在，请检查路径或重新选择。','影像导入失败：文件或目录不存在，请检查路径或重新选择。'),
    ('model','模型加载失败：权重不匹配','模型加载失败：权重不匹配'),
    ('export','导出失败：无法写入','导出失败：无法写入'),
    (None,'请重新选择文件。','请重新选择文件。'),
])
def test_operation_prefix_is_precise_and_not_duplicated(kind,reason,expected):
    assert operation_error(kind,reason)==expected


def test_task_error_uses_active_operation_but_not_a_previous_task(workbench,monkeypatch):
    from geoforma.controllers.tasks import TaskWorkflow
    w,app,wait,errors=workbench;messages=[]
    monkeypatch.setattr(w.statusBar(),'report_error',lambda text,*args,**kwargs:messages.append(text))
    w.task_kind='export';w.progress.model.begin('导出标签','export')
    TaskWorkflow.error(w,'PermissionError: [WinError 5] Access denied')
    assert messages[-1]=='标签导出失败：没有访问权限，请检查文件或目录权限。'
    w.progress.model.finish('failed')
    TaskWorkflow.error(w,'ValueError: 请选择类别。')
    assert messages[-1]=='请选择类别。'
    w.task_kind=None


def test_project_loading_error_retains_context_after_progress_finishes(workbench,monkeypatch):
    from geoforma.controllers.tasks import TaskWorkflow
    w,app,wait,errors=workbench;messages=[]
    monkeypatch.setattr(w.statusBar(),'report_error',lambda text,*args,**kwargs:messages.append(text))
    w.progress.model.begin('打开项目','project_open');w.progress.model.finish('failed')
    w.loading_task=object()
    try:
        TaskWorkflow.error(w,'FileNotFoundError: [Errno 2] missing')
        assert messages[-1]=='打开项目失败：文件或目录不存在，请检查路径或重新选择。'
    finally:w.loading_task=None
