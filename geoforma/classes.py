"""User-defined categories with stable references and editable export values."""


def class_value(category):
    return category.get('value',category['id'])


def next_class_value(classes):
    values={class_value(category) for category in classes}
    following=max(values,default=0)+1
    return following if following<=65534 else next((value for value in range(1,65535) if value not in values),65535)


def class_values(classes):
    validate_classes(classes)
    return {category['id']:class_value(category) for category in classes}


def validate_classes(classes):
    if not isinstance(classes,(list,tuple)):raise ValueError('类别列表格式无效。')
    ids, names, values = set(), set(), set()
    for item in classes:
        if not isinstance(item,dict) or 'id' not in item or not isinstance(item.get('name'),str):raise ValueError('类别格式无效。')
        identifier, name = item['id'], item['name'].strip()
        if type(identifier) is not int or not 1 <= identifier <= 65534 or identifier in ids:
            raise ValueError('类别编号必须唯一，范围为 1–65534。')
        if not name or name.casefold() in names:
            raise ValueError('类别名称不能为空或重复。')
        value=class_value(item)
        if type(value) is not int or not 1<=value<=65534 or value in values:
            raise ValueError('标签值必须唯一，范围为 1–65534。')
        if 'color' in item:
            from .class_colors import normalize_color
            normalize_color(item['color'])
        ids.add(identifier); names.add(name.casefold());values.add(value)


def next_class_id(project):
    return max(project.get('next_class_id', 1), max((c['id'] for c in project['classes']), default=0) + 1)


def referenced_class_ids(labels, *histories):
    used = {label.get('class_id') for label in labels}
    for history in histories:
        for entries in history:
            for _, label, _ in entries:
                if label:used.add(label.get('class_id'))
    return used - {None}
