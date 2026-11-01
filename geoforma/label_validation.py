"""Leaf validation for label geometry and finite editing strokes; no UI/storage imports."""
import math
from shapely.geometry import shape


def validate_stroke(stroke,allow_empty=False):
    if not isinstance(stroke,(list,tuple)) or len(stroke)>8192:raise ValueError('编辑线格式错误或点数过多。')
    if not allow_empty and len(stroke)<2:raise ValueError('编辑线至少需要两个点。')
    for point in stroke:
        if not isinstance(point,(list,tuple)) or len(point)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) for v in point):raise ValueError('编辑线坐标必须为有限数值。')


def validate_label(label,image_ids,class_ids=None):
    if not isinstance(label,dict) or not isinstance(label.get('id'),str) or not label['id']:raise ValueError('标签 ID 无效。')
    if label.get('image_id') not in image_ids:raise ValueError('标签引用了不存在的影像。')
    if label.get('status') not in ('candidate','confirmed'):raise ValueError('标签状态无效。')
    if label.get('score') is not None:
        from .contracts import finite_number
        if not finite_number(label['score']):raise ValueError('标签模型分数必须为有限数值。')
    category=label.get('class_id')
    if category is not None and (type(category) is not int or not 1<=category<=65534 or class_ids is not None and category not in class_ids):raise ValueError('标签引用了无效类别。')
    if label.get('editing_state','model') not in ('model','manual'):raise ValueError('人工编辑状态无效。')
    if 'annotation_mode' in label and label['annotation_mode'] not in ('individual','automatic'):raise ValueError('标签标注模式无效。')
    if 'manual_edits' in label and (not isinstance(label['manual_edits'],list) or any(not isinstance(edit,dict) for edit in label['manual_edits'])):raise ValueError('人工编辑来源记录无效。')
    try:g=shape(label['geometry'])
    except Exception as error:raise ValueError('标签几何格式无效。') from error
    if g.geom_type not in ('Polygon','MultiPolygon') or g.is_empty or not g.is_valid or not math.isfinite(g.area) or not all(math.isfinite(v) for v in g.bounds):raise ValueError('标签必须为有效的多边形，不会静默修复。')
    for field in ('source_geometry','raw_geometry'):
        if field in label and (field=='source_geometry' or label[field] is not None):
            source={k:v for k,v in label.items() if k not in ('source_geometry','raw_geometry')}
            source['geometry']=label[field];validate_label(source,image_ids,class_ids)


