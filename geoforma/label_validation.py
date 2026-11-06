"""Leaf validation for label geometry and finite editing strokes; no UI/storage imports."""
import math
from shapely.geometry import shape


def reject_legacy_geometry(label):
    if any(field in label for field in ('source_geometry','raw_geometry')):
        raise ValueError('标签包含不再支持的旧轮廓字段。')


def reject_project_legacy_geometry(project):
    """Check label-bearing records only, without treating metadata as labels."""
    def label(record):
        if isinstance(record,dict):reject_legacy_geometry(record)

    def entries(value):
        if not isinstance(value,(list,tuple)):return
        for entry in value:
            if isinstance(entry,(list,tuple)) and len(entry)==3:
                label(entry[1])

    def draft(value):
        if not isinstance(value,dict):return
        label(value)
        entries(value.get('_label_entries'))
        if '_draft' in value:draft(value['_draft'])
        batch=value.get('reshape_batch')
        if isinstance(batch,(list,tuple)):
            for item in batch:draft(item)

    if not isinstance(project,dict):return
    labels=project.get('labels',())
    if isinstance(labels,(list,tuple)):
        for record in labels:label(record)
    workspace=project.get('workspace',{})
    if isinstance(workspace,dict):draft(workspace.get('draft'))
    images=project.get('images',())
    if isinstance(images,(list,tuple)):
        for image in images:
            if not isinstance(image,dict):continue
            draft(image.get('working_draft'))
            sessions=image.get('mode_sessions',{})
            if not isinstance(sessions,dict):continue
            for session in sessions.values():
                if not isinstance(session,dict):continue
                draft(session.get('draft'))
                for name in ('undo','redo'):
                    stack=session.get(name,())
                    if isinstance(stack,(list,tuple)):
                        for item in stack:draft(item)
    history=project.get('history',{})
    histories=history.get('labels',{}) if isinstance(history,dict) else {}
    if isinstance(histories,dict):
        for record in histories.values():
            if not isinstance(record,dict):continue
            for name in ('undo','redo'):
                stack=record.get(name,())
                if isinstance(stack,(list,tuple)):
                    for operation in stack:entries(operation)


def validate_stroke(stroke,allow_empty=False):
    if not isinstance(stroke,(list,tuple)) or len(stroke)>8192:raise ValueError('编辑线格式错误或点数过多。')
    if not allow_empty and len(stroke)<2:raise ValueError('编辑线至少需要两个点。')
    for point in stroke:
        if not isinstance(point,(list,tuple)) or len(point)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) for v in point):raise ValueError('编辑线坐标必须为有限数值。')


def validate_label(label,image_ids,class_ids=None):
    if not isinstance(label,dict) or not isinstance(label.get('id'),str) or not label['id']:raise ValueError('标签 ID 无效。')
    reject_legacy_geometry(label)
    if label.get('image_id') not in image_ids:raise ValueError('标签引用了不存在的影像。')
    if label.get('status')!='confirmed':raise ValueError('标签状态无效。')
    model=label.get('model',{})
    if not isinstance(model,dict):raise ValueError('标签模型记录无效。')
    if 'single_polygon' in model and type(model['single_polygon']) is not bool:raise ValueError('标签单一多边形设置无效。')
    from .session_validation import validate_prompts
    validate_prompts(label)
    if label.get('score') is not None:
        from .contracts import finite_number
        if not finite_number(label['score']):raise ValueError('标签模型分数必须为有限数值。')
    category=label.get('class_id')
    if category is not None and (type(category) is not int or not 1<=category<=65534 or class_ids is not None and category not in class_ids):raise ValueError('标签引用了无效类别。')
    if label.get('editing_state','model') not in ('model','manual'):raise ValueError('人工编辑状态无效。')
    if 'annotation_mode' in label and label['annotation_mode']!='individual':raise ValueError('标签标注模式无效。')
    if 'manual_edits' in label and (not isinstance(label['manual_edits'],list) or any(not isinstance(edit,dict) for edit in label['manual_edits'])):raise ValueError('人工编辑来源记录无效。')
    try:g=shape(label['geometry'])
    except Exception as error:raise ValueError('标签几何格式无效。') from error
    if g.geom_type not in ('Polygon','MultiPolygon') or g.is_empty or not g.is_valid or not math.isfinite(g.area) or not all(math.isfinite(v) for v in g.bounds):raise ValueError('标签必须为有效的多边形，不会静默修复。')
    return g


