"""Stable task identities and concise, non-repeating status details."""
import re

TASK_NAMES={
    'import':'导入影像',
    'reference_import':'导入参考',
    'model':'加载模型',
    'model_warmup':'加载模型',
    'preparation':'准备影像',
    'cache_cleanup':'清理旧缓存',
    'interactive':'逐个分割',
    'history':'撤销标签',
    'reshape':'重塑轮廓',
    'manual_polygon':'生成多边形',
    'bands':'调整波段',
    'export':'导出标签',
    'project_open':'打开项目',
    'project_recovery':'恢复工作',
    'startup':'启动软件',
    'shutdown':'退出清理',
    'runtime_probe':'检查环境',
    'runtime_install':'安装环境',
    'runtime_remove':'移除环境',
    'resource_install':'配置资源',
}


def task_name(kind):
    return TASK_NAMES.get(kind,'正在处理')


def progress_name(kind,stage=''):
    """Name the work represented by the adjacent meter, including model stages."""
    if kind=='preparation':
        clean=_plain(stage)
        if clean=='检查完整影像缓存':return '检查影像缓存'
        if clean=='检查影像引用与模型':return '检查输入'
        if clean in ('加载 SAM 模型','加载模型','加载模型权重','初始化模型进程'):
            return _STAGES.get(clean,clean)
        return '影像预处理'
    if kind=='interactive':return task_name(kind)
    model_stage=kind in ('model','model_warmup')
    if model_stage and any(word in stage for word in ('下载','官方源','续传')):return '下载模型'
    if model_stage and '加载 SAM 模型' in stage:return '加载模型'
    return task_name(kind)


_TITLE_ALIASES={
    'history':('全部撤销标签',),
    'interactive':('根据提示生成轮廓',), 'bands':('准备波段与拉伸',),
    'cache_cleanup':('清理旧项目的影像缓存',),
    'resource_install':('配置',),
}
_STAGES={
    '正在读取影像与 VRT 引用':'读取文件引用', '读取参考影像与 VRT 引用':'读取文件引用',
    '加载 SAM 模型':'加载模型', '加载模型权重':'读取模型权重',
    '检查完整影像缓存':'检查影像缓存', '按像元网格重塑轮廓':'重塑轮廓',
    '导出原始网格标签':'写入文件', '检查影像引用与模型':'检查输入',
    '初始化模型进程':'初始化推理', '清理旧项目的影像缓存':'清理旧缓存',
}


def _plain(value):return str(value or '').strip().rstrip('….').strip()


def task_subject(title,kind=None):
    """Strip only known action prefixes at a delimiter, never inside a filename."""
    title=_plain(title)
    if kind=='reference_import' and title.startswith('导入 ') and title.endswith(' 参考影像'):
        return title[len('导入 '):-len(' 参考影像')]
    for action in (task_name(kind),)+_TITLE_ALIASES.get(kind,()):
        if title==action:return ''
        for separator in ('：',': ',' · ',' ','…：','…: '):
            if title.startswith(action+separator):return title[len(action+separator):].strip()
    return title


def task_detail(title,stage='',kind=None,model=None):
    """Describe the current action and object without relying on another widget."""
    subject=task_subject(title,kind);stage=_plain(stage)
    if kind=='preparation' and model and stage in ('加载 SAM 模型','加载模型','加载模型权重','初始化模型进程'):
        action=_STAGES.get(stage,stage)
        return action+' · '+model+(' · 影像：'+subject if subject else '')
    if kind=='preparation' and model and any(word in stage for word in ('下载','校验','验证权重')):
        if model not in stage:stage+=' · '+model
        return stage+(' · 影像：'+subject if subject else '')
    stage=_STAGES.get(stage,stage)
    # Remove worker counters only from recognized task phrases. Paths, model
    # versions, image dimensions and byte counts must remain intact.
    match=re.fullmatch(r'(导入影像|准备影像)\s+\d+\s*/\s*\d+(?:[：:]\s*(.*))?',stage)
    if match:stage=match.group(1)+(' · '+match.group(2) if match.group(2) else '')
    stage=re.sub(r'^(缓存标签轮廓) · \d+\s*/\s*\d+$',r'\1',stage)
    stage=re.sub(r'^分割窗口 (\d+×\d+)；编码或复用特征$',r'处理区域 \1 像素',stage)
    if not stage:stage=task_name(kind)
    # The adjacent badge already identifies the overall preparation task.
    # Show the image alone for its ordinary stage, but keep distinct phases.
    if kind=='preparation' and subject and stage in ('准备影像','准备影像 · '+subject):return subject
    # Import workers report a bare filename; retain the action alongside it.
    if kind in ('import','reference_import') and not stage.startswith(task_name(kind)+' · ') and re.search(r'\.(?:tif|tiff|vrt)$',stage,re.IGNORECASE):
        stage=task_name(kind)+' · '+stage
    if stage==subject:return task_name(kind)+' · '+subject
    if stage==_plain(title):return stage
    if not subject:return stage
    if re.search(r'(?:^| · )'+re.escape(subject)+r'(?=$| · )',stage):return stage
    if subject in stage.split(' · '):return stage
    if any(stage==verb+' '+subject or stage.startswith(verb+' '+subject+' · ') for verb in ('下载','校验','安装','加载','准备','导入','导出')):return stage
    for separator in ('：',' · '):
        if stage.endswith(separator+subject):return stage
    return stage+' · '+subject


def visible_detail(title,stage='',kind=None,model=None):
    """The badge already names the task; details only add new information."""
    detail=task_detail(title,stage,kind,model)
    badge=progress_name(kind,stage)
    if detail==badge:return ''
    if detail.startswith(badge+' · '):return detail[len(badge)+3:]
    return detail


def task_message(title,stage='',kind=None,model=None,count=''):
    """Object and counts accompany the action shown beside the progress bar."""
    detail=visible_detail(title,stage,kind,model)
    return ' · '.join(value for value in (detail,count) if value)
