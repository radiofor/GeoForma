"""Persisted per-label manual editing policy."""
import copy
from datetime import datetime

MANUAL_PROMPT_LOCK_MESSAGE='当前轮廓已人工编辑，请取消编辑后新建标注。'
def manual_label(label):return bool(label and label.get('editing_state')=='manual')


def referenced_draft_classes(*records):
    """Keep classes referenced by pending edits and composite undo/redo alive."""
    used=set()
    def visit(record):
        if isinstance(record,(list,tuple)):
            for item in record:visit(item)
        elif isinstance(record,dict):
            used.update(record.get(key) for key in ('class_id','initial_class_id'))
            used.update(record.get('part_classes',{}).values())
            for key in ('reshape_batch','_draft','_label_entries','draft','undo','redo','working_draft'):visit(record.get(key))
            for session in record.get('mode_sessions',{}).values():visit(session)
    for record in records:visit(record)
    return used-{None}


def batch_labels(labels,draft):
    """Present staged contours without reusing bounds or paths from saved ones."""
    batch={d.get('base_id'):d for d in draft.get('reshape_batch',[]) if d.get('base_id')}
    result=[]
    for label in labels:
        if label['id'] in batch:
            label={k:v for k,v in label.items() if k not in ('_bounds','_render_path','_source_geometry','_source_path')}
            label.update(geometry=batch[label['id']]['geometry'],editing_state='manual')
        result.append(label)
    return result

def require_model_editable(request):
    if request.get('editing_state')=='manual':raise ValueError(MANUAL_PROMPT_LOCK_MESSAGE)


def draft_snapshot(draft):
    return {k:copy.deepcopy(v) for k,v in draft.items() if k not in ('logits','choices')}


def geometry_history(undo,redo):
    return any(stack and '_draft' in stack[-1] for stack in (undo,redo))


def reshaped_label(label,result):
    """Build a detached saved label without copying the superseded contour."""
    transient=('geometry','_bounds','_render_path','_source_geometry','_source_path',
               'raw_geometry','source_geometry','smoothing_applied','seed_geometry')
    updated=copy.deepcopy({key:value for key,value in label.items() if key not in transient})
    updated.update(geometry=result['geometry'],editing_state='manual',edge=False)
    updated['manual_edits']=[*updated.get('manual_edits',[]),{'tool':'raster_reshape','stroke':copy.deepcopy(result['stroke']),
        'alternate':result['alternate'],'window':list(result['window']),'added_pixels':result['added_pixels'],
        'removed_pixels':result['removed_pixels'],'at':datetime.now().isoformat()}]
    return updated
