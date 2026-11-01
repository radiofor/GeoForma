"""One-time extraction of panel builders and scene layers."""
import ast,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

# Panel builders are separate from workflow controllers and drawing code.
path=ROOT/'geoforma/panels.py';source=path.read_text(encoding='utf-8');module=ast.parse(source);lines=source.splitlines(keepends=True)
header=''.join(lines[:next(n.lineno for n in module.body if isinstance(n,ast.FunctionDef))-1])
header=re.sub(r'\bfrom \.(\w+)',r'from ...\1',header)
header=header.replace('from ...ui.label_table','from ..label_table')
folder=ROOT/'geoforma/ui/panels';folder.mkdir(exist_ok=True)
(folder/'__init__.py').write_text('"""Panel builders with explicit workbench command bindings."""\n',encoding='utf-8')
for node,filename in [(n,{'left':'imagery','right':'annotation','bottom':'status'}[n.name]) for n in module.body if isinstance(n,ast.FunctionDef)]:
    body=''.join(lines[node.lineno-1:node.end_lineno]);body=re.sub(r'\bfrom \.(\w+)',r'from ...\1',body).replace('from ...ui.label_table','from ..label_table')
    if node.name=='right':
        chunks=[]
        marks=[('build_candidates','    w.auto_group='),('build_editor','    w.editor_group='),('build_label_list','    row=QHBoxLayout();w.label_filter='),('build_export','    export_group=')]
        end='    w.editor_scroll='
        for i,(name,mark) in enumerate(marks):
            start=body.index(mark);stop=body.index(marks[i+1][1] if i+1<len(marks) else end,start)
            chunks.append((name,body[start:stop]));body=body[:start]+f'    {name}(w,layout)\n'+body[stop:]
        body+='\n\n'+'\n\n'.join(f'def {name}(w,layout):\n'+text for name,text in chunks)
    (folder/(filename+'.py')).write_text(header+body+'\n',encoding='utf-8')
path.write_text('"""Public compatibility entry points for the modular panel builders."""\nfrom .ui.panels.imagery import left\nfrom .ui.panels.annotation import right\nfrom .ui.panels.status import bottom\n',encoding='utf-8')

# The viewport owns input and transforms; SceneLayers owns persistent graphics items.
path=ROOT/'geoforma/viewport.py';source=path.read_text(encoding='utf-8');module=ast.parse(source);lines=source.splitlines(keepends=True)
cls=next(n for n in module.body if isinstance(n,ast.ClassDef));geometry=next(n for n in module.body if isinstance(n,ast.FunctionDef))
names={'show_raster','clear_preview','show_preview','cached_path','set_overlay_visibility','overlays','prompts','hit_label'}
fields=['base_item','detail_item','preview_item','overlay_records','overlay_items','prompt_items','point_records','box_item','path_cache','overlay_visible']
parts=[n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in names]
original_header=''.join(lines[:geometry.lineno-1]);original_header=re.sub(r'\bfrom \.(\w+)',r'from ..\1',original_header)
layer_class='class SceneLayers:\n    def __init__(self,view):\n        self.view=view;self.reset()\n\n    def reset(self):\n        self.base_item=None;self.detail_item=None;self.preview_item=None;self.overlay_records={};self.overlay_items=[];self.prompt_items=[];self.point_records={};self.box_item=None;self.path_cache=OrderedDict();self.overlay_visible=True\n\n    def scene(self):return self.view.scene()\n    def mapToScene(self,*args):return self.view.mapToScene(*args)\n    def viewport(self):return self.view.viewport()\n    def transform(self):return self.view.transform()\n\n'
bodies='\n'.join(re.sub(r'\bfrom \.(\w+)',r'from ..\1',''.join(lines[n.lineno-1:n.end_lineno])) for n in parts)
(ROOT/'geoforma/rendering/scene_layers.py').write_text('"""Incremental graphics layers; no annotation state or model inference."""\n'+original_header+''.join(lines[geometry.lineno-1:geometry.end_lineno])+'\n\n'+layer_class+bodies+'\n',encoding='utf-8')
for node in sorted(parts,key=lambda n:n.lineno,reverse=True):
    args=ast.unparse(node.args);call=','.join(a.arg for a in node.args.args[1:])
    lines[node.lineno-1:node.end_lineno]=[f'    def {node.name}({args}):return self.layers.{node.name}({call})\n']
source=''.join(lines)
start=source.index('def geometry_path(');end=source.index('class ImageView',start)
source=source[:start]+'from .rendering.scene_layers import SceneLayers,geometry_path\n\n\n'+source[end:]
source=source.replace("self.base_item=None;self.detail_item=None;self.preview_item=None;self.overlay_items=[];self.prompt_items=[];self.drag_start=None;self.rubber=None;self.drag_pixel=None;self.drag_add=False","self.layers=SceneLayers(self);self.drag_start=None;self.rubber=None;self.drag_pixel=None;self.drag_add=False")
source=source.replace('self.overlay_records={};self.path_cache=OrderedDict();self.overlay_visible=True;self.temporary_mode=None;self.middle_drag=None','self.temporary_mode=None;self.middle_drag=None')
source=source.replace('        self.point_records={};self.box_item=None\n','')
source=source.replace('self.scene().clear();self.preview_item=None;self.base_item=None;self.detail_item=None;self.overlay_items=[];self.prompt_items=[];self.rubber=None;self.overlay_records.clear();self.path_cache.clear()','self.scene().clear();self.layers.reset();self.rubber=None')
source=source.replace('        self.point_records.clear();self.box_item=None\n','')
source+='\n'+ '\n'.join(f'    @property\n    def {field}(self):return self.layers.{field}\n' for field in fields)
path.write_text(source,encoding='utf-8')
print('Panels split; scene layers extracted')
