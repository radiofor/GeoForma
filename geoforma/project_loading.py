"""Prepare a complete first project frame without mutating the live workbench."""
import copy,math
from dataclasses import dataclass
from pathlib import Path
from .storage import load_project
from .label_index import LabelIndex


@dataclass
class LoadedProject:
    project:dict
    image:dict|None
    mode_index:int
    draft:dict
    index:object
    layer:int=0
    frame:object=None
    window:object=None
    size:int=1400
    navigation:object=None
    view_window:object=None
    smoothing:object=None
    draft_path:object=None
    overview:object=None


def prepare_project(path,viewport_size,task=None,read_frame=True,project=None):
    def check():
        if task:task.check()
    def stage(text,current=0,total=0):
        check()
        if task:task.signals.progress.emit(current,total,text)
    stage('读取项目文件：'+Path(path).name);project=load_project(path) if project is None else project
    from .cache_recovery import remap_migrated_checkpoint
    remap_migrated_checkpoint(project)
    state=project.get('workspace',{})
    image=next((im for im in project['images'] if im['id']==state.get('image_id')),next(iter(project['images']),None))
    mode_index=0;mode='individual';session=(image or {}).get('mode_sessions',{}).get(mode,{})
    draft=copy.deepcopy(state.get('draft') or session.get('draft') or {})
    if draft.get('base_id') and not draft.get('seed_geometry'):
        original=next((l for l in project['labels'] if l['id']==draft['base_id']),None)
        if original:draft['seed_geometry']=copy.deepcopy(original['geometry'])
    loaded=LoadedProject(project,image,mode_index,draft,None,navigation=state.get('navigation') or session.get('navigation'),
                         view_window=state.get('view_window') or session.get('view'))
    if image is None:
        loaded.index=LabelIndex([]);return loaded
    check()
    labels=[l for l in project['labels'] if l['image_id']==image['id']]
    stage(f'准备标签索引 · {len(labels)} 个目标')
    loaded.index=LabelIndex(labels,task=task)
    visible=loaded.index.visible(draft)
    from .rendering.scene_layers import geometry_path
    if draft.get('geometry'):loaded.draft_path=geometry_path(draft['geometry'])
    stage(f'缓存标签轮廓 · {len(visible)} 个目标')
    for i,label in enumerate(visible):
        check();label['_render_path']=geometry_path(label['geometry'])
        if (i+1)%256==0:stage(f'缓存标签轮廓 · {i+1}/{len(visible)}',i+1,len(visible))
    from .smoothing import settings,smooth_batch
    config=settings(project,mode)
    if config['enabled']:
        stage('准备平滑轮廓')
        saved=loaded.index.visible({})
        sources=[l for l in saved if not (draft.get('geometry') and l['id']==draft.get('base_id'))]
        if draft.get('geometry'):
            sources.append({'id':'__draft','geometry':draft['geometry'],'box':draft.get('box'),'status':'draft','editing_state':draft.get('editing_state','model'),
                            'model':{'single_polygon':not mode_index and state.get('single_polygon',False)}})
        from .rendering.smoothing_queue import prepare_paths
        loaded.smoothing=(sources,prepare_paths(sources,smooth_batch(sources,config['value'],image,task),task))
    check()
    if read_frame and image.get('display_recipe'):
        width,height=viewport_size;size=max(800,min(2200,max(width,height)*2));loaded.size=size
        window=[0,0,image['width'],image['height']]
        if loaded.navigation:
            scale=loaded.navigation['scale'];cx,cy=loaded.navigation['center'];pad=32
            x0=max(0,math.floor(cx-(width/2+pad)/scale));y0=max(0,math.floor(cy-(height/2+pad)/scale))
            x1=min(image['width'],math.ceil(cx+(width/2+pad)/scale));y1=min(image['height'],math.ceil(cy+(height/2+pad)/scale))
            if x1>x0 and y1>y0:window=[x0,y0,x1-x0,y1-y0]
        elif loaded.view_window:
            x,y,w,h=loaded.view_window;pad=math.ceil(max(w/max(1,width),h/max(1,height))*32)
            x0=max(0,x-pad);y0=max(0,y-pad);x1=min(image['width'],x+w+pad);y1=min(image['height'],y+h+pad)
            if x1>x0 and y1>y0:window=[x0,y0,x1-x0,y1-y0]
        from .raster import read_rgb
        full=[0,0,image['width'],image['height']]
        if window!=full:
            stage('加载全图预览：'+image['name']);loaded.overview=read_rgb(image,full,image['display_recipe'],min(size,1600))
        stage('加载视图影像：'+image['name']);loaded.window=window;loaded.frame=read_rgb(image,window,image['display_recipe'],size)
    stage('恢复视图与编辑状态');return loaded
