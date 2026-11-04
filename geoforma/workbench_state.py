"""Explicit application state shared by desktop workflows; no QWidget references."""
from dataclasses import dataclass,field
from pathlib import Path


@dataclass
class WorkbenchState:
    project:dict
    project_path:Path|None=None
    image:dict|None=None
    draft:dict=field(default_factory=dict)
    reshape_session:dict|None=None
    prompt_undo:list=field(default_factory=list)
    prompt_redo:list=field(default_factory=list)
    label_undo:list=field(default_factory=list)
    label_redo:list=field(default_factory=list)
    selected_id:str|None=None
    selected_ids:set=field(default_factory=set)
    selected_points:set=field(default_factory=set)
    image_sessions:dict=field(default_factory=dict)
    runtime_status:dict|None=None
    dirty:bool=False
    dirty_revision:int=0
    project_epoch:int=0
    closing:bool=False
    last_error:str=''
    mode_index:int=0
    mode_histories:dict=field(default_factory=dict)
    tool_modes:dict=field(default_factory=dict)
    model_warmup_signature:str|None=None
    label_indexes:dict=field(default_factory=dict)
