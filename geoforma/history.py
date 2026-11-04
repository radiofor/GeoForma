"""JSON history contracts and snapshots; geometry values are immutable records."""
INDIVIDUAL='individual'


def label_stack_snapshot(stack):
    return [[(identifier,dict(old) if old is not None else None,index) for identifier,old,index in entries] for entries in stack]


def history_snapshot(history):
    result={'schema':1,'labels':{mode:{name:label_stack_snapshot(record.get(name,[])) for name in ('undo','redo')}
                               for mode,record in history.get('labels',{}).items()}}
    if 'scope' in history:result['scope']=history['scope']
    return result


def validate_history(project):
    """Reject malformed history before it can change a saved label or another mode."""
    images={image['id']:image for image in project['images']}
    class_ids={category['id'] for category in project['classes']}
    live={label['id']:label for label in project['labels']}
    history=project.get('history')
    if history is not None:
        if not isinstance(history,dict) or history.get('schema')!=1 or not isinstance(history.get('labels'),dict):
            raise ValueError('项目撤销记录版本或格式无效。')
        scope=history.get('scope','separate_modes')
        if scope not in ('separate_modes','all_labels'):raise ValueError('项目标签历史范围无效。')
        for mode,record in history['labels'].items():
            if mode!=INDIVIDUAL or not isinstance(record,dict):raise ValueError('项目撤销记录的模式无效。')
            for name in ('undo','redo'):
                stack=record.get(name,[])
                if not isinstance(stack,list):raise ValueError('项目标签历史格式无效。')
                for entries in stack:
                    if not isinstance(entries,list) or not entries:raise ValueError('项目标签历史操作为空或格式无效。')
                    seen=set()
                    for entry in entries:
                        if not isinstance(entry,(list,tuple)) or len(entry)!=3:raise ValueError('项目标签历史条目无效。')
                        identifier,old,index=entry
                        if not isinstance(identifier,str) or not identifier or identifier in seen or type(index) is not int or index<0:
                            raise ValueError('项目标签历史的 ID 或位置无效。')
                        seen.add(identifier)
                        candidate=old if old is not None else live.get(identifier)
                        if candidate is not None:
                            if not isinstance(candidate,dict) or candidate.get('id')!=identifier or candidate.get('image_id') not in images:
                                raise ValueError('项目标签历史引用了无效标签或影像。')
                            if scope!='all_labels' and candidate.get('annotation_mode',INDIVIDUAL)!=mode:raise ValueError('项目标签历史不能跨标注模式。')
                            if old is not None and scope!='all_labels':old['annotation_mode']=mode
                            if old is not None:
                                from .label_validation import validate_label
                                validate_label(old,set(images),class_ids)
    for image in images.values():
        for session in image.get('mode_sessions',{}).values():
            for name in ('undo','redo'):
                stack=session.get(name,[])
                if not isinstance(stack,list) or any(not isinstance(entry,dict) or set(entry)-{'points','box','window','ignore_seed','_draft','_label_entries'} for entry in stack):
                    raise ValueError('项目提示历史格式无效。')
                for entry in stack:
                    if '_draft' in entry:
                        from .session_validation import validate_draft
                        draft=entry['_draft']
                        if not isinstance(draft,dict):raise ValueError('轮廓撤销记录无效。')
                        validate_draft(draft,image['id'],set(images),live)
