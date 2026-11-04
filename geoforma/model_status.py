"""Cheap UI checks and conservative budgets; never loads Torch or hashes gigabytes."""
from .ui.text import ui_text
import math
from pathlib import Path
from .weights import default_checkpoint
from .resource_state import inspect_checkpoint


def weight_status(spec,path=None):
    try:
        path=Path(path or default_checkpoint(spec['variant'],spec['backend']))
    except (OSError,ValueError):return ui_text('resources.unavailable'),Path(spec['file'])
    state=inspect_checkpoint(spec,path)
    key={'missing':'model_status.weight_status.007','configured':'model_status.weight_status.005',
         'local':'model_status.weight_status.003','incomplete':'model_status.weight_status.006','unavailable':'resources.unavailable'}[state['availability']]
    return ui_text(key),path


def memory_budget(spec,mode='interaction'):
    profile=spec['memory_profile']
    peak=profile[mode+'_peak_mib']
    return math.ceil((peak*profile['budget_margin']+profile['budget_extra_mib'])/1024*2)/2


def memory_description(spec,cpu=False):
    if cpu:return ui_text('model_status.memory_description.004')
    return ui_text('model_status.memory_description.001').format(p0=memory_budget(spec))


def memory_tooltip(spec):
    p=spec['memory_profile']
    return ui_text('model_status.memory_tooltip.002').format(p0=p['interaction_peak_mib']/1024)
