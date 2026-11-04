"""Shared toolbar eligibility for both buttons and keyboard shortcuts."""

TOOLS=frozenset(('positive','negative','box','select_points','select','pan','reshape','draw_polygon'))
PROMPT_TOOLS=frozenset(('positive','negative','box','select_points'))


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
        'draw_polygon':bool(image and not busy and window.raw_view_action.isChecked() and window.reshape_session is None),
        'reshape':bool(image and not busy and window.raw_view_action.isChecked()
                       and not window.draft.get('pending')),
    }
    if window.draft.get('manual_vertices'):
        for tool in tools:
            if tool not in ('draw_polygon','pan'):tools[tool]=False
    return tools
