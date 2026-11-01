"""Pure multipart draft deletion; saved labels and history are owned by callers."""
import copy
from shapely.geometry import shape,mapping
from shapely.ops import unary_union


def remove_parts(draft,records,deleted):
    remaining=[]
    for current in draft.get('reshape_batch') or [draft]:
        if current.get('base_id') in deleted:continue
        ids=current.get('display_ids',[])
        parts=[d for d in records if ids and d['_draft_root']==ids[0] and d['id'] not in deleted]
        if not parts:
            if not current.get('geometry') and current:remaining.append(copy.deepcopy(current))
            continue
        item=copy.deepcopy(current);item.pop('reshape_batch',None)
        item.update(geometry=mapping(unary_union([shape(d['geometry']) for d in parts])),display_ids=[d['id'] for d in parts])
        remaining.append(item)
    result=dict(remaining[0]) if remaining else {}
    if len(remaining)>1:result['reshape_batch']=remaining
    return result
