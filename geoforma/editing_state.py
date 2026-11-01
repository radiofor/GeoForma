"""Persisted per-label manual editing policy."""
import copy
from datetime import datetime
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
    if request.get('editing_state')=='manual':raise ValueError('人工编辑的标签不能重新运行 SAM，请先撤销人工修改。')


def draft_snapshot(draft):
    return {k:copy.deepcopy(v) for k,v in draft.items() if k not in ('logits','choices')}


def geometry_history(undo,redo):
    return any(stack and '_draft' in stack[-1] for stack in (undo,redo))


def label_draft(label,class_id):
    """Detach mutable prompts from the saved record before staging an edit."""
    return {'base_id':label['id'],'geometry':label['geometry'],'seed_geometry':label['geometry'],
        'window':copy.deepcopy(label.get('window')),'points':copy.deepcopy(label.get('points') or []),
        'box':copy.deepcopy(label.get('box')),'edge':label.get('edge',False),'score':label.get('score'),
        'model_metadata':copy.deepcopy(label.get('model',{})),'editing_state':label.get('editing_state','model'),
        'manual_edits':copy.deepcopy(label.get('manual_edits',[])),'class_id':label.get('class_id') or class_id,
        'source':label.get('source','interactive')}


def stage_manual_edit(draft,result):
    """Replace immutable geometry and provenance; never persist or invoke a model."""
    staged={k:v for k,v in draft.items() if k not in ('logits','choices')}
    staged.update(geometry=result['geometry'],editing_state='manual',edge=False,pending=False)
    staged['manual_edits']=[*draft.get('manual_edits',[]),{'tool':'raster_reshape','stroke':copy.deepcopy(result['stroke']),
        'alternate':result['alternate'],'window':list(result['window']),'added_pixels':result['added_pixels'],
        'removed_pixels':result['removed_pixels'],'at':datetime.now().isoformat()}]
    return staged
