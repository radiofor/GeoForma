"""Turn technical exceptions into concise, actionable user-facing messages.

The original diagnostic belongs in the caller's log; this function never
changes it. Domain-specific messages remain intact so users retain the
reason and instructions supplied by the operation that failed.
"""
import re

_EXCEPTION=re.compile(r'^(?P<kind>[A-Za-z_][\w.]*(?:Error|Exception|Timeout)):\s*(?P<detail>.*)$')
_OS_CODE=re.compile(r'\[(WinError|Errno)\s+(\d+)\]',re.IGNORECASE)
_CHINESE=re.compile(r'[\u3400-\u9fff]')
_OPERATIONS={
    'import':('影像导入失败',('导入影像失败','影像导入失败','导入失败')),
    'reference_import':('参考影像导入失败',('参考影像导入失败','导入参考失败')),
    'model':('模型加载失败',('模型加载失败','加载模型失败')),
    'model_warmup':('模型加载失败',('模型加载失败','加载模型失败')),
    'preparation':('影像预处理失败',('影像预处理失败','预处理失败')),
    'interactive':('标注生成失败',('标注生成失败','生成标注失败','分割失败')),
    'reshape':('重塑失败',('重塑失败','重塑轮廓失败')),
    'manual_polygon':('多边形生成失败',('多边形生成失败','生成多边形失败')),
    'bands':('波段配置失败',('波段配置失败','调整波段失败')),
    'export':('标签导出失败',('标签导出失败','导出标签失败','导出失败')),
    'project_open':('打开项目失败',('打开项目失败','项目打开失败')),
    'project_recovery':('恢复工作失败',('恢复工作失败','恢复项目失败')),
    'resource_install':('资源配置失败',('资源配置失败','配置资源失败')),
    'cache_cleanup':('缓存清理失败',('缓存清理失败','清理缓存失败')),
    'history':('撤销标签失败',('撤销标签失败','撤销失败')),
}


def operation_error(kind,message):
    """Add the active operation once, leaving operation-specific reasons intact."""
    detail=str(message).strip()
    item=_OPERATIONS.get(kind)
    if item is None:return detail
    label,aliases=item
    if any(alias in detail for alias in aliases):return detail
    return label+('：'+detail if detail else '')


def user_message(diagnostic):
    if isinstance(diagnostic,BaseException):
        diagnostic=f'{type(diagnostic).__name__}: {diagnostic}'
    lines=str(diagnostic).strip().splitlines()
    if not lines:return '操作未完成，请重试。'
    line=lines[-1].strip();match=_EXCEPTION.match(line)
    if not match:
        return '操作未完成，请重试。' if line.startswith(('Traceback (','File "','During handling')) else line
    kind=match.group('kind').rsplit('.',1)[-1];detail=match.group('detail').strip()
    code=_OS_CODE.search(detail)
    system=code.group(1).lower() if code else None
    number=int(code.group(2)) if code else None
    # Explicit, actionable domain explanations are more useful than a generic
    # exception class. Windows' localized system errors have an OS code and
    # are handled below instead of being mistaken for such explanations.
    if _CHINESE.search(detail) and (not code or re.search(r'请|重新|检查|选择|移回',detail)):
        return _OS_CODE.sub('',detail).strip(' :：')
    if kind=='PermissionError' or (system,number) in (('winerror',5),('errno',13)):return '没有访问权限，请检查文件或目录权限。'
    if kind=='FileNotFoundError' or (system,number) in (('winerror',2),('winerror',3),('errno',2)):return '文件或目录不存在，请检查路径或重新选择。'
    if kind in ('TimeoutError','ConnectTimeout','ReadTimeout'):return '操作超时，请稍后重试。'
    if kind in ('ConnectionError','ConnectionRefusedError','ConnectionResetError','ConnectionAbortedError','HTTPError'):
        return '连接失败，请检查网络后重试。'
    if (system,number) in (('errno',28),('winerror',39),('winerror',112)):return '磁盘空间不足，请释放空间后重试。'
    if system=='winerror' and number in (32,33):return '文件正被其他程序占用，请关闭相关程序后重试。'
    if system=='winerror' and number==13:return '文件数据无效，请检查文件后重试。'
    if kind=='OSError' and code:return '系统操作失败，请检查相关文件或设置后重试。'
    return detail or '操作未完成，请重试。'
