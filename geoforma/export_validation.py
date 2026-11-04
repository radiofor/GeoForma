"""Shared safety checks for labels exported against a single image."""
from .classes import class_values
from .label_validation import validate_label
from .label_conflicts import assert_no_overlaps


def validate_export_labels(image,labels,classes,task):
    values=class_values(classes or [])
    image_id=image.get('id');identifiers=set();geometries=[]
    class_ids=set(values) if classes is not None else None
    for label in labels:
        task.check()
        if not isinstance(label,dict) or label.get('status')!='confirmed':raise ValueError('只能导出已保存的标签。')
        if type(label.get('class_id')) is not int or not 1<=label['class_id']<=65534:
            raise ValueError('导出标签必须指定有效类别。')
        if classes is not None and label['class_id'] not in values:raise ValueError('导出标签引用了不存在的类别。')
        if label.get('image_id')!=image_id:raise ValueError('导出标签不属于当前影像。')
        geometry=validate_label(label,{image_id},class_ids)
        x0,y0,x1,y1=geometry.bounds
        if x0 < -1e-7 or y0 < -1e-7 or x1 > image['width']+1e-7 or y1 > image['height']+1e-7:
            raise ValueError('导出标签超出当前影像范围，请调整后重新保存。')
        if label['id'] in identifiers:raise ValueError('导出标签编号重复。')
        identifiers.add(label['id']);geometries.append(geometry)
    assert_no_overlaps(labels,task,geometries)
    return values,geometries
