"""Inference orchestration; contains no Qt objects or process lifecycle code."""
from ..domain import tiles
from ..raster import read_rgb, validate_source
from ..contracts import ModelBackend,validate_window


class ModelEngine:
    def __init__(self):
        self.backend:ModelBackend|None=None;self.input_cache=None

    def prepare_model(self,config,task):
        from ..weights import ensure_checkpoint
        config['checkpoint']=ensure_checkpoint(config,task);task.check()
        task.signals.progress.emit(0,0,'加载 SAM 模型…')
        from ..execution_policy import resolve_execution
        execution=resolve_execution(config)
        config=dict(config,execution=execution)
        family=config.get('backend','sam')
        if self.backend is None or getattr(self.backend,'execution','native')!=execution or getattr(self.backend,'family','sam')!=family:
            self.close()
            from ..backend_factory import create_backend
            self.backend=create_backend(config)
        self.backend.load(config);task.check()
        return {'checkpoint':config['checkpoint'],'device':self.backend.config['device'],'execution':execution}

    def close(self):
        self.input_cache=None
        if self.backend is not None:
            close=getattr(self.backend,'close',None)
            if close:close()
            self.backend=None

    def prepare_backend(self,config,image,task):
        task.check();task.signals.progress.emit(0,0,'检查影像引用与模型…')
        missing,current=validate_source(image)
        if current!=image['fingerprint']:raise ValueError('影像源文件已变化。请重新导入后预处理，避免使用过期缓存。')
        if missing is not None and (image.get('model_recipe') or {}).get('validity_policy')!={'kind':'declared_missing_v1','value':missing}:
            raise ValueError('影像的缺失值处理尚未更新。请重新打开项目或重新设置模型波段后准备影像。')
        from ..feature_cache import feature_directory
        from ..resource_location import require_resource_dir
        feature_directory(require_resource_dir())
        self.prepare_model(config,task)

    def preprocess(self,image,config,bounds,task):
        self.input_cache=None
        try:return self._preprocess(image,config,bounds,task)
        finally:
            self.input_cache=None
            release=getattr(self.backend,'release_image',None)
            if release:release()

    def _preprocess(self,image,config,bounds,task):
        from ..workflow import full_bounds,tile_count,check_cache_space
        self.prepare_backend(config,image,task);bounds=full_bounds(image);count=tile_count(image)
        from ..feature_cache import feature_directory
        from ..resource_location import require_resource_dir
        root=require_resource_dir();folder=feature_directory(root)
        # Preflight only uncached features; do not reject a completed cache on a full disk.
        if count>4096:
            existing=0
            for path in folder.glob('*.pt'):
                existing+=1
                if existing%1000==0:task.check()
            check_cache_space(root,max(0,count-existing),getattr(self.backend,'cache_bytes',4*1024*1024))
        missing=0
        for index,window in enumerate(tiles(bounds,image['width'],image['height'])):
            if index%64==0:task.check();task.signals.progress.emit(index,count,'检查完整影像缓存')
            if not (folder/(self.backend.key(image,window)+'.pt')).exists():missing+=1
        check_cache_space(root,missing,getattr(self.backend,'cache_bytes',4*1024*1024))
        hits=0;processed=0
        windows=tiles(bounds,image['width'],image['height'])
        for i,window in enumerate(windows):
            task.check()
            # Valid cached features need no raster read; the adapter reads only on a miss.
            hits+=self.backend.encode(image,window,None)
            processed+=1;task.signals.progress.emit(i+1,count,f'准备影像 {i+1}/{count}')
        return {'count':processed,'hits':hits,'device':self.backend.config['device'],'checkpoint':config['checkpoint'],'bounds':bounds}

    def predict(self,image,config,request,task):
        if request.get('full_image'):raise ValueError('全图分割功能已移除，请逐个标注目标。')
        from ..editing_state import require_model_editable
        require_model_editable(request)
        from ..session_validation import validate_prompts
        validate_prompts(request)
        self.prepare_backend(config,image,task)
        from ..prompt_bounds import bounded_points
        request=dict(request,points=bounded_points(request['points'],request.get('box')))
        window=request['window'];task.signals.progress.emit(0,0,f'分割窗口 {window[2]}×{window[3]}；编码或复用特征…')
        rgb,valid=self.window_input(image,window)
        args=(image,window,rgb,valid,request['points'],request.get('box'),request.get('logits'),request.get('seed'))
        preview=getattr(task.signals,'preview',None)
        def emit_preview(value):
            if request.get('fill_holes'):
                from ..hole_filling import fill_preview
                value=dict(value,mask=fill_preview(value['mask'],valid))
            preview.emit(value)
        result=self.backend.predict(*args,on_mask=emit_preview if preview else None,single_polygon=bool(request.get('single_polygon'))) if getattr(self.backend,'streaming_preview',False) else self.backend.predict(*args)
        if request.get('single_polygon') or request.get('box'):
            from ..single_polygon import constrain_choice
            choices=[constrain_choice(choice,request['points'],bool(request.get('single_polygon')),request.get('box')) for choice in result['choices']]
            result['choices']=[choice for choice in choices if choice is not None]
        if request.get('fill_holes'):
            from ..hole_filling import fill_prediction
            from shapely.geometry import shape
            choices=[]
            for choice in result['choices']:
                task.check();geometry=fill_prediction(choice['geometry'],valid,window)
                if geometry:choices.append(dict(choice,geometry=geometry,pixels=int(round(shape(geometry).area))))
            result['choices']=choices
        result['checkpoint']=config['checkpoint'];task.check();return result



    def window_input(self,image,window):
        validate_window(window,8192)
        key=self.backend.key(image,window)
        if self.input_cache is None or self.input_cache[0]!=key:
            rgb,valid=read_rgb(image,window);self.input_cache=(key,rgb,valid)
        return self.input_cache[1:]

    def preview(self,image,config,request,task):
        from ..editing_state import require_model_editable
        require_model_editable(request)
        from ..session_validation import validate_prompts
        validate_prompts(request)
        self.prepare_backend(config,image,task)
        window=request['window']
        # Dragging never encodes uncached, potentially large windows.
        if not self.backend.restore(image,window):return None
        rgb,valid=self.window_input(image,window)
        kwargs={'single_polygon':True} if request.get('single_polygon') else {}
        result=self.backend.predict(image,window,rgb,valid,request['points'],request.get('box'),None,request.get('seed'),True,**kwargs)
        if request.get('fill_holes') and result is not None:
            from ..hole_filling import fill_preview
            result=dict(result,mask=fill_preview(result['mask'],valid))
        task.check();return result

