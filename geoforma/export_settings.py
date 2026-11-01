"""Project-level vector export settings and field-name validation."""
import re

DEFAULT_LABEL_FIELD='class_value'
RESERVED_FIELDS={'label_id','class_name','status','source','method','model','prompts',
                 'edit_state','edit_count','edits','smooth_px','image_id','fid','ogc_fid',
                 'geom','geometry','rowid','_rowid_','oid'}


def validate_label_field(value,suffix=''):
    if not isinstance(value,str):raise ValueError('标签字段名必须为文本。')
    value=value.strip()
    if not re.fullmatch(r'[^\W\d]\w*',value) or len(value.encode('utf-8'))>63:
        raise ValueError('标签字段名须以字母、汉字或下划线开头，仅含字母、汉字、数字和下划线，最多 63 个 UTF-8 字节。')
    if value.casefold() in RESERVED_FIELDS:raise ValueError('标签字段名与导出保留字段重复，请使用其他名称。')
    if suffix.lower()=='.shp' and len(value.encode('utf-8'))>10:
        raise ValueError('SHP 标签字段名最多 10 个 UTF-8 字节，请缩短名称或改用 GPKG/GeoJSON。')
    return value


def label_field(project):
    return validate_label_field(project.get('export_label_field',DEFAULT_LABEL_FIELD))


def target_crs(project,image=None):
    if project.get('export_crs'):return project['export_crs']
    images=project.get('images',());first=next(iter(images),image or {})
    crs=first.get('assigned_crs') or first.get('crs') or ''
    if images and not crs:raise ValueError('第一个栅格未设置投影，请先指定该栅格投影或修改导出投影。')
    return crs
