"""Shared toolbar eligibility for both buttons and keyboard shortcuts."""

TOOLS=frozenset(('positive','negative','box','select_points','select','pan','reshape','draw_polygon'))
PROMPT_TOOLS=frozenset(('positive','negative','box','select_points'))


def has_unsaved_annotation(draft):
    """A draft or in-progress annotation must be resolved before reshaping."""
    return any(draft.get(key) for key in ('geometry','base_id','points','box','manual_vertices','reshape_batch','pending'))


def has_reshape_target(window):
    """A saved label and no unfinished annotation are required for reshape."""
    return bool(window.image and window.current_labels() and not has_unsaved_annotation(window.draft))


def reshape_presentation_pending(window):
    """Do not edit an outline retained from an older geometry or option."""
    if getattr(window,'_reshape_smoothing_hold',None):return True
    context=window.annotation_context()
    return bool(getattr(window,'_presentation_failed_context',None)==context or
                (getattr(window,'_presentation_transition_pending',False)
                 and not getattr(window,'_presentation_ready',True)
                 and getattr(window,'_presentation_transition_context',None)==context))


def compatible_tool(tool,mode):
    return isinstance(tool,str) and tool in TOOLS and mode=='individual'


def restored_tool(preferred,current,mode):
    """Temporary busy/ready/manual states disable tools without replacing choices."""
    for tool in (preferred,current):
        if compatible_tool(tool,mode):return tool
    return 'pan'


def available_tools(window):
    from .operation_state import interaction_locked,can_browse,background_prefetch
    if interaction_locked(window):return dict.fromkeys(TOOLS,False)
    busy=window.task is not None and not background_prefetch(window)
    image=window.image
    prompt=bool(image and image.get('ready') and window.prompt_target_available()
                and not window.prompt_task_busy()
                and not window.model_prompts_locked(include_reshape=False))
    tools={
        **dict.fromkeys(('positive','negative','box','select_points'),prompt),
        'select':can_browse(window),
        'pan':True,
        'draw_polygon':bool(image and not busy and window.raw_view_action.isChecked()
                            and (not has_unsaved_annotation(window.draft) or bool(window.draft.get('manual_vertices')))),
        'reshape':bool(not busy and window.raw_view_action.isChecked() and has_reshape_target(window)
                       and not reshape_presentation_pending(window)),
    }
    if window.draft.get('manual_vertices'):
        for tool in tools:
            if tool not in ('draw_polygon','pan'):tools[tool]=False
    return tools
