import copy
import json
import os,time
from pathlib import Path
from .atomic_io import atomic_target,atomic_copy,read_json
from .source_catalog import SourceGuard,project_sources,relocate_sources
from .class_colors import normalize_color


def project_snapshot(project):
    """Detach mutable records; saved geometry/point arrays are immutable domain values.

    The background writer performs the expensive deep copy and JSON serialization.
    Editing replaces label records, never mutates a stored geometry in place.
    """
    snapshot=dict(project);snapshot['_snapshot_time_ns']=time.time_ns()
    snapshot['model']=dict(project['model'])
    snapshot['classes']=[dict(c) for c in project['classes']]
    snapshot['labels']=[dict(label) for label in project['labels']]
    snapshot['workspace']=copy.deepcopy(project.get('workspace',{}))
    if 'references' in project:snapshot['references']=copy.deepcopy(project['references'])
    if 'smoothing' in project:snapshot['smoothing']=copy.deepcopy(project['smoothing'])
    if 'history' in project:
        from .history import history_snapshot
        snapshot['history']=history_snapshot(project['history'])
    snapshot['images']=[]
    for image in project['images']:
        record=copy.deepcopy({k:v for k,v in image.items() if k not in ('working_draft','mode_sessions')})
        if 'working_draft' in image:record['working_draft']=dict(image['working_draft'])
        if 'mode_sessions' in image:record['mode_sessions']={mode:{**session,'draft':dict(session.get('draft',{})),
            'undo':[dict(entry) for entry in session.get('undo',[])],'redo':[dict(entry) for entry in session.get('redo',[])]}
            for mode,session in image['mode_sessions'].items()}
        snapshot['images'].append(record)
    return snapshot


def save_project(project, path, backup=True):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    outputs=[path,path.with_name(path.name+'.bak')] if backup else [path]
    SourceGuard(project_sources(project)).check(*outputs)
    payload=copy.deepcopy(project)
    from .classes import validate_classes
    from .export_settings import label_field
    validate_classes(payload['classes']);payload['export_label_field']=label_field(payload)
    for category in payload['classes']:
        if 'color' in category:category['color']=normalize_color(category['color'])
    captured=payload.pop('_snapshot_time_ns',None);now=time.time_ns()
    captured=captured if type(captured) is int and 0<captured<=now else now
    if any(config.get('enabled') for config in payload.get('smoothing',{}).values()) or any('source_geometry' in label for label in payload['labels']):
        from .smoothing import stored_labels
        payload['labels']=stored_labels(payload)
    relocate_sources(payload,path.parent,relative=True)
    with atomic_target(path) as part:
        with part.open('w',encoding='utf-8') as stream:json.dump(payload,stream,ensure_ascii=False,indent=2,allow_nan=False)
        if backup and path.exists():atomic_copy(path,path.with_name(path.name+'.bak'))
        # Recovery order represents when the state was captured, not when a slow
        # background writer happened to finish after a newer manual save.
        os.utime(part,ns=(captured,captured))


def load_project(path):
    path=Path(path);project=read_json(path,max_bytes=256*1024**2)
    from .project_validation import validate_project
    validate_project(project)
    # Older projects could contain fractional settings. Migrate the actual
    # smoothing value as well as the control so previews and exports agree.
    from .smoothing import integer_value
    for config in project.get('smoothing',{}).values():config['value']=integer_value(config['value'])
    if 'cache_id' not in project:
        from .domain import digest
        original=str(path.resolve())
        while original.casefold().endswith(('.autosave','.bak')):original=original.rsplit('.',1)[0]
        project['cache_id']=digest({'project_path':original.casefold()})
    for category in project['classes']:
        if 'color' in category:category['color']=normalize_color(category['color'])
    from .model_preferences import normalize_model
    project['model']={**project['model'],**normalize_model(project['model'])}
    # Older projects kept an inactive custom value behind a separate pin flag.
    if project.pop('export_crs_fixed',True) is False:project['export_crs']=''
    project.setdefault('export_crs','')
    from .export_settings import label_field
    project['export_label_field']=label_field(project)
    from .annotation_modes import migrate_modes
    migrate_modes(project)
    for label in project['labels']:
        if 'source_geometry' in label:
            label['geometry']=label.pop('source_geometry');label.pop('smoothing_applied',None)
    relocate_sources(project,path.parent)
    image_ids={i['id'] for i in project['images']}
    for label in project['labels']:
        if label['image_id'] not in image_ids:raise ValueError('标签引用了不存在的影像。')
    from .history import validate_history
    validate_history(project)
    return project
