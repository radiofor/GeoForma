"""Validate restored prompts before they reach Qt controls or raster allocation."""
from .contracts import finite_number,validate_window


def validate_navigation(value):
    if value is None:return
    if not isinstance(value,dict) or not finite_number(value.get('scale')) or not 1e-9<value['scale']<=64:
        raise ValueError('视图缩放状态无效。')
    center=value.get('center')
    if not isinstance(center,(list,tuple)) or len(center)!=2 or not all(finite_number(v) for v in center):raise ValueError('视图中心位置无效。')


def validate_prompts(record):
    points=record.get('points')
    if points is not None:
        from .prompt_bounds import validate_points
        validate_points(points)
    box=record.get('box')
    if box is not None and (not isinstance(box,(list,tuple)) or len(box)!=4 or not all(finite_number(v) for v in box) or box[2]<=box[0] or box[3]<=box[1]):raise ValueError('框选范围无效。')
    if record.get('window') is not None:validate_window(record['window'],8192)


def validate_draft(draft,image_id,image_ids,labels,class_ids=None):
    if not isinstance(draft,dict):raise ValueError('当前轮廓状态必须为对象。')
    validate_prompts(draft)
    category=draft.get('class_id')
    if category is not None and (type(category) is not int or not 1<=category<=65534 or class_ids is not None and category not in class_ids):
        raise ValueError('未保存标注引用了无效类别。')
    if 'part_classes' in draft:
        values=draft['part_classes']
        if not isinstance(values,dict) or any(not isinstance(k,str) or type(v) is not int or not 1<=v<=65534 for k,v in values.items()):
            raise ValueError('未保存标注类别无效。')
        if class_ids is not None and any(v not in class_ids for v in values.values()):raise ValueError('未保存标注引用了无效类别。')
    if 'display_ids' in draft:
        ids=draft['display_ids']
        if not isinstance(ids,list) or any(not isinstance(i,str) or not i for i in ids) or len(set(ids))!=len(ids):
            raise ValueError('未保存标注编号无效。')
        base=draft.get('base_id')
        if any(i in labels and i!=base for i in ids) or base and ids and ids[0]!=base:
            raise ValueError('未保存标注编号与已有标签冲突。')
    if 'reshape_batch' in draft:
        batch=draft['reshape_batch']
        if not isinstance(batch,list) or len(batch)<2 or any(not isinstance(d,dict) or 'reshape_batch' in d or not d.get('geometry') for d in batch):
            raise ValueError('批量重塑状态无效。')
        used=set()
        for item in batch:
            validate_draft(item,image_id,image_ids,labels,class_ids)
            identities=set(item.get('display_ids',[]))|({item['base_id']} if item.get('base_id') else set())
            if used&identities:raise ValueError('批量重塑不能重复引用同一标签。')
            used.update(identities)
    if 'manual_vertices' in draft:
        from .label_validation import validate_stroke
        validate_stroke(draft['manual_vertices'],allow_empty=True)
    base=draft.get('base_id')
    if base is not None and (not isinstance(base,str) or base in labels and labels[base]['image_id']!=image_id):raise ValueError('当前轮廓引用了其他影像的标签。')
    if draft.get('editing_state','model') not in ('model','manual'):raise ValueError('当前轮廓的人工编辑状态无效。')
    for name in ('geometry','seed_geometry'):
        if draft.get(name) is not None:
            from .label_validation import validate_label
            validate_label({**draft,'id':'draft','image_id':image_id,'status':'confirmed','geometry':draft[name]},image_ids,class_ids)
    for flag in ('pending','ignore_seed'):
        if draft.get(flag) is not None and type(draft[flag]) is not bool:raise ValueError('当前轮廓的操作状态无效。')


def validate_sessions(project):
    images={i['id']:i for i in project['images']};labels={l['id']:l for l in project['labels']}
    class_ids={c['id'] for c in project['classes']}
    for image in images.values():
        sessions=image.get('mode_sessions',{})
        if not isinstance(sessions,dict):raise ValueError('影像工作状态无效。')
        if 'working_draft' in image:validate_draft(image['working_draft'],image['id'],set(images),labels,class_ids)
        for mode,session in sessions.items():
            if mode!='individual' or not isinstance(session,dict):raise ValueError('标注模式工作状态无效。')
            validate_draft(session.get('draft',{}),image['id'],set(images),labels,class_ids)
            if session.get('view') is not None:validate_window(session['view'])
            validate_navigation(session.get('navigation'))
            selected=session.get('selected_ids',[])
            if not isinstance(selected,list) or not all(isinstance(v,str) for v in selected):raise ValueError('选中标签列表无效。')
            for name in ('undo','redo'):
                stack=session.get(name,[])
                if not isinstance(stack,list):raise ValueError('提示撤销记录无效。')
                for entry in stack:
                    if not isinstance(entry,dict):raise ValueError('提示撤销记录无效。')
                    if '_label_entries' in entry and '_draft' not in entry:raise ValueError('复合编辑历史缺少草稿快照。')
                    validate_prompts(entry)
                    if '_draft' in entry:
                        if set(entry)-{'_draft','_label_entries'}:raise ValueError('轮廓撤销记录不能混用其他提示字段。')
                        if '_label_entries' in entry:
                            from .label_history import validate_entries
                            validate_entries(entry['_label_entries'],image['id'],labels,class_ids)
                        validate_draft(entry['_draft'],image['id'],set(images),labels,class_ids)
    workspace=project.get('workspace',{});image_id=workspace.get('image_id')
    if image_id is not None and image_id not in images:raise ValueError('工作状态引用了不存在的影像。')
    validate_draft(workspace.get('draft',{}),image_id,set(images),labels,class_ids)
    if workspace.get('view_window') is not None:validate_window(workspace['view_window'])
    validate_navigation(workspace.get('navigation'))
    if workspace.get('operation',0)!=0:raise ValueError('工作状态的标注模式无效。')
    from .tool_state import compatible_tool
    if 'tool' in workspace and not compatible_tool(workspace['tool'],'individual'):raise ValueError('工作状态的工具无效。')
    tools=workspace.get('tools',{})
    if not isinstance(tools,dict) or any(mode!='individual' or not compatible_tool(tool,mode) for mode,tool in tools.items()):raise ValueError('标注模式的工具记录无效。')
    for flag in ('auto_apply','single_polygon','preparation_paused','raw_view'):
        if flag in workspace and type(workspace[flag]) is not bool:raise ValueError('工作状态的选项无效。')
