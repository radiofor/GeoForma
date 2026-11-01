"""One transition gate for UI shortcuts and controller entry points."""


def interaction_locked(window):
    # The signal-blocked commit restores tools through the same public APIs.
    return bool(getattr(window,'closing',False) or
                not getattr(window,'restoring_project',False) and
                (getattr(window,'loading_task',None) or getattr(window,'project_transition',None)))


def background_prefetch(window):
    image=getattr(window,'image',None)
    pending=getattr(window,'pending_prefetch_work',None)
    return bool(getattr(window,'task',None) is not None and getattr(window,'task_kind',None)=='preparation'
                and image and image.get('ready') and getattr(window,'preparing_id',None)!=image.get('id')
                and (not pending or pending[2]))


def can_start_operation(window):
    return not (getattr(window,'task',None) or getattr(window,'closing',False) or
                getattr(window,'loading_task',None) or getattr(window,'project_transition',None))


def can_browse(window):
    """Model loading and prefetching allow navigation to another image."""
    return not interaction_locked(window) and (getattr(window,'task',None) is None or
                                             getattr(window,'task_kind',None) in ('model','model_warmup','preparation'))
