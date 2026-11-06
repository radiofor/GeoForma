"""Validate file data before it can replace the active workspace."""
import math
from .label_validation import validate_label,validate_stroke


def validate_project(project):
    if not isinstance(project,dict) or type(project.get('schema')) is not int or project['schema']!=1:raise ValueError('不支持的项目版本。')
    from .label_validation import reject_project_legacy_geometry
    reject_project_legacy_geometry(project)
    if 'export_crs_fixed' in project:raise ValueError('项目包含不支持的导出设置。')
    from .project_cache import OWNER_PATTERN
    if not isinstance(project.get('cache_id'),str) or not OWNER_PATTERN.fullmatch(project['cache_id']):raise ValueError('项目缓存标识无效。')
    from .reference_images import validate_references
    validate_references(project)
    if not isinstance(project.get('model'),dict):raise ValueError('项目模型配置无效。')
    if 'smoothing' in project:
        from .smoothing import validate_settings
        if not isinstance(project['smoothing'],dict) or any(mode!='individual' for mode in project['smoothing']):raise ValueError('平滑模式无效。')
        for config in project['smoothing'].values():validate_settings(config)
    from .model_preferences import normalize_model
    try:normalize_model(project['model'])
    except (KeyError,TypeError,ValueError) as error:raise ValueError('项目模型配置无效。') from error
    for name in ('images','labels','classes'):
        if not isinstance(project.get(name),list):raise ValueError('项目列表格式无效。')
    from .classes import validate_classes
    validate_classes(project['classes']);classes={category['id'] for category in project['classes']}
    from .export_settings import label_field
    label_field(project)
    next_id=project.get('next_class_id',1)
    if type(next_id) is not int or not 1<=next_id<=65535:raise ValueError('下一类别编号无效。')
    ids=set()
    for image in project['images']:
        if not isinstance(image,dict) or not isinstance(image.get('id'),str) or not image['id'] or image['id'] in ids:raise ValueError('影像 ID 为空或重复。')
        if {'candidate_runs','dismissed_candidates'} & image.keys():raise ValueError('影像包含不支持的标注记录。')
        ids.add(image['id'])
        if not isinstance(image.get('path'),str) or not image['path'] or '\x00' in image['path']:raise ValueError('影像引用路径无效。')
        if any(type(image.get(key)) is not int or image[key]<=0 for key in ('width','height')):raise ValueError('影像尺寸无效。')
        transform=image.get('transform')
        if not isinstance(transform,(list,tuple)) or len(transform)!=6 or any(type(v) not in (int,float) or not math.isfinite(v) for v in transform):raise ValueError('影像仿射变换无效。')
        if transform[0]*transform[4]-transform[1]*transform[3]==0:raise ValueError('影像仿射变换不可逆。')
        from .raster_metadata import validate_metadata
        validate_metadata(image)
    labels=set()
    for label in project['labels']:
        validate_label(label,ids,classes)
        if label['id'] in labels:raise ValueError('标签 ID 重复。')
        labels.add(label['id'])
    workspace=project.get('workspace',{})
    if not isinstance(workspace,dict):raise ValueError('工作状态格式无效。')
    if {'candidate_range','candidate_layer','auto_regenerate'} & workspace.keys() or workspace.get('annotation_mode','individual')!='individual':raise ValueError('工作状态包含不支持的标注设置。')
    from .session_validation import validate_sessions
    validate_sessions(project)
    manual=workspace.get('reshape')
    if manual is not None:
        if not isinstance(manual,dict) or manual.get('target','label') not in ('label','draft','auto'):raise ValueError('重塑状态引用了无效标签。')
        if manual.get('target')=='draft':
            draft=workspace.get('draft')
            if not isinstance(draft,dict):raise ValueError('重塑状态引用了无效轮廓。')
            validate_label({**draft,'id':'draft','image_id':workspace.get('image_id'),'status':'confirmed'},ids)
        elif manual.get('target')!='auto' and manual.get('label_id') not in labels:raise ValueError('重塑状态引用了无效标签。')
        validate_stroke(manual.get('stroke'),allow_empty=True)
        validate_stroke(manual.get('redo_stroke',[]),allow_empty=True)
