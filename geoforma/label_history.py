"""Pure label-history replay; safe to execute on immutable worker snapshots."""
import copy


def validate_entries(entries,image_id,labels,class_ids=None):
    """Validate composite edit history before it can overwrite another image."""
    from .label_validation import validate_label
    if not isinstance(entries,list):raise ValueError('标签编辑历史无效。')
    seen=set()
    for entry in entries:
        if not isinstance(entry,(list,tuple)) or len(entry)!=3:raise ValueError('标签编辑历史无效。')
        identifier,old,index=entry
        if not isinstance(identifier,str) or not identifier or identifier in seen or type(index) is not int or index<0:raise ValueError('标签编辑历史无效。')
        seen.add(identifier)
        if old is not None:
            if not isinstance(old,dict) or old.get('id')!=identifier:raise ValueError('标签编辑历史编号无效。')
            validate_label(old,{image_id},class_ids)
        if identifier in labels and labels[identifier]['image_id']!=image_id:raise ValueError('标签编辑历史引用了其他影像。')


def restore_entries(labels,entries):
    current={label['id']:(index,label) for index,label in enumerate(labels)}
    identifiers={entry[0] for entry in entries};reverse=[]
    for identifier,old,index in entries:
        present=current.get(identifier)
        reverse.append((identifier,copy.deepcopy(present[1]) if present else None,present[0] if present else index))
    result=[label for label in labels if label['id'] not in identifiers]
    for identifier,old,index in sorted(entries,key=lambda entry:entry[2]):
        if old:result.insert(index,old)
    return result,reverse


