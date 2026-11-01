"""Separate interactive objects from automatic review results, including legacy projects."""
INDIVIDUAL='individual'
AUTOMATIC='automatic'


def label_mode(label,image=None):
    explicit=label.get('annotation_mode')
    if explicit in (INDIVIDUAL,AUTOMATIC):return explicit
    if label.get('status')=='candidate' or label.get('source') in ('automatic','prompt_guided','automatic_review'):return AUTOMATIC
    if image and any(label['id'] in run.get('label_ids',()) for run in image.get('candidate_runs',{}).values()):return AUTOMATIC
    return INDIVIDUAL


def migrate_modes(project):
    images={i['id']:i for i in project['images']}
    project['labels']=[dict(label,annotation_mode=label_mode(label,images.get(label['image_id']))) for label in project['labels']]
    labels={l['id']:l for l in project['labels']}
    for image in images.values():
        legacy=image.get('working_draft',{})
        if legacy and not image.get('mode_sessions'):
            base=labels.get(legacy.get('base_id'));mode=label_mode(base,image) if base else INDIVIDUAL
            image['mode_sessions']={mode:{'draft':dict(legacy)}}
    workspace=project.get('workspace',{});draft=workspace.get('draft',{})
    if draft and not workspace.get('annotation_mode') and (draft.get('points') or draft.get('box')):
        image=images.get(workspace.get('image_id'))
        if image:
            # Retain old full-image prompts for recovery, without activating them.
            mode=AUTOMATIC if workspace.get('operation')==1 else INDIVIDUAL
            image.setdefault('mode_sessions',{}).setdefault(mode,{'draft':dict(draft)})
            if mode==AUTOMATIC:workspace['draft']={}
