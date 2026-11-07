"""Pinned original SAM adapter. SAM 2 requires its own adapter/cache schema."""
import hashlib
import os
from pathlib import Path
import numpy as np
import torch
from rasterio.features import rasterize
from rasterio.transform import Affine
from .pixel_geometry import mask_geometry

from .domain import digest
from .prompt_bounds import bounded_points,bounded_mask,clip_geometry
from .single_polygon import single_mask,preview_bitmap


def atomic_torch(payload,path):
    from .atomic_io import atomic_target
    with atomic_target(path) as part:torch.save(payload,part)


class SamBackend:
    family='sam'
    execution='native'
    streaming_preview=True
    cache_bytes=4*1024*1024
    schema='meta_sam_v1_dca509fe_fp32_v1'

    def __init__(self):
        self.model=None;self.config=None;self.signature=None;self.predictor=None;self.cache_key=None

    def load(self, config, on_load=None):
        if config.get('backend','sam')!='sam':raise ValueError('SAM 1 适配器不能加载其他代际，请选择匹配的模型后端。')
        path=Path(config['checkpoint'])
        if not path.is_file():raise FileNotFoundError('权重文件不可访问，请重试自动下载。')
        stamp=(str(path.resolve()),path.stat().st_size,path.stat().st_mtime_ns,config['variant'],config['device'])
        if stamp==self.signature:return
        if on_load:on_load()
        from segment_anything import sam_model_registry,SamPredictor
        device=config['device']
        if device=='cuda' and not torch.cuda.is_available():device='cpu'
        torch.set_num_threads(min(8,os.cpu_count() or 4))
        self.model=None;self.predictor=None;self.cache_key=None;self.signature=None
        if torch.cuda.is_available():torch.cuda.empty_cache()
        model=sam_model_registry[config['variant']]()
        model.requires_grad_(False)
        state=torch.load(path,map_location='cpu',weights_only=True)
        model.load_state_dict(state,strict=True);del state
        fallback=None
        try:self.model=model.eval().to(device)
        except RuntimeError as error:
            if device!='cuda':raise
            fallback=str(error);device='cpu';self.model=model.eval().to(device)
            try:torch.cuda.empty_cache()
            except RuntimeError:pass
        self.predictor=SamPredictor(self.model)
        with path.open('rb') as stream:weight_hash=hashlib.file_digest(stream,'sha256').hexdigest()
        self.config={**config,'device':device,'weights_sha256':weight_hash,'fallback_reason':fallback};self.signature=stamp

    def descriptor(self,image,window):
        return {'schema':self.schema,'source':image['fingerprint'],'grid':[image['width'],image['height'],image['transform']],
            'recipe':image['model_recipe'],'window':list(window),'weights':self.config['weights_sha256'],'variant':self.config['variant']}

    def key(self,image,window):return digest(self.descriptor(image,window))

    def restore(self,image,window):
        from .feature_cache import feature_path
        from .resource_location import require_resource_dir
        key=self.key(image,window);path=feature_path(require_resource_dir(),key)
        if key==self.cache_key:return True
        payload=None
        if path.exists():
            try:
                from .feature_cache import load_features
                payload=load_features(path,self.cache_bytes)
                if payload is None:return False
                if (payload['key']!=key or payload.get('metadata')!=self.descriptor(image,window) or
                    tuple(payload['features'].shape)!=(1,256,64,64) or payload['features'].dtype!=torch.float32 or
                    tuple(payload['original_size'])!=(window[3],window[2])):payload=None
            except Exception:payload=None
        if payload is None:return False
        with torch.inference_mode():
            p=self.predictor;p.reset_image();p.features=payload['features'].to(self.model.device)
            p.original_size=tuple(payload['original_size']);p.input_size=tuple(payload['input_size']);p.is_image_set=True
        self.cache_key=key
        return True

    def encode(self,image,window,rgb=None):
        if self.restore(image,window):return True
        if rgb is None:
            from .raster import read_rgb
            rgb,_=read_rgb(image,window)
        from .feature_cache import feature_path,check_rewrite_space
        from .resource_location import require_resource_dir
        root=require_resource_dir();key=self.key(image,window);path=feature_path(root,key)
        check_rewrite_space(root,path,self.cache_bytes)
        with torch.inference_mode():
            self.predictor.set_image(rgb)
            atomic_torch({'key':key,'metadata':self.descriptor(image,window),'source_path':image['path'],
                'source_crs':image.get('assigned_crs') or image['crs'],'features':self.predictor.get_image_embedding().cpu(),
                'original_size':list(self.predictor.original_size),'input_size':list(self.predictor.input_size)},path)
        self.cache_key=key;return False

    def close(self):
        self.model=None;self.predictor=None;self.cache_key=None;self.signature=None
        if torch.cuda.is_available():torch.cuda.empty_cache()

    def release_image(self):
        """Drop decoded feature tensors while keeping weights and disk caches."""
        if self.predictor is not None:self.predictor.reset_image()
        self.cache_key=None
        if torch.cuda.is_available():torch.cuda.empty_cache()

    def predict(self,image,window,rgb,valid,points,box=None,logits=None,seed=None,preview=False,on_mask=None,single_polygon=False):
        points=bounded_points(points,box)
        hit=self.encode(image,window,rgb);p=self.predictor
        # Scene coordinates use pixel edges; SAM point indices use pixel centers.
        coords=np.array([[x-window[0]-.5,y-window[1]-.5] for x,y,_ in points],np.float32) if points else None
        labels=np.array([label for _,_,label in points]) if points else None
        localbox=np.array([box[0]-window[0],box[1]-window[1],box[2]-window[0],box[3]-window[1]],np.float32) if box else None
        prior=logits
        if prior is None and seed:
            mask=rasterize([(seed,1)],out_shape=rgb.shape[:2],transform=Affine.translation(window[0],window[1]))
            encoder=getattr(p.model,'sam_prompt_encoder',getattr(p.model,'prompt_encoder',None))
            size=getattr(encoder,'mask_input_size',(256,256))
            prior=torch.nn.functional.interpolate(torch.from_numpy(np.where(mask,4.,-4.).astype(np.float32))[None,None],size=size,mode='bilinear',align_corners=False)[0].numpy()
        anchor=image.get('_prompt_anchor')
        with torch.inference_mode():
            masks,scores,low=p.predict(point_coords=coords,point_labels=labels,box=localbox,mask_input=prior,multimask_output=prior is None and not preview and (anchor is not None or len(points)<=1 and box is None))
        if preview:
            mask=bounded_mask(np.asarray(masks[0],dtype=bool)&valid,window,box)
            if single_polygon:
                mask=single_mask(mask,window,points)
            bitmap=preview_bitmap(mask,window,points,single_polygon,max_size=image.get('_preview_size',256))
            return {'mask':bitmap,'window':list(window),'box':box,'single_polygon':bool(single_polygon)}
        # Select by prompt consistency, then SAM score, before expensive polygonization.
        def rank(i):
            mask=bounded_mask(np.asarray(masks[i],dtype=bool)&valid,window,box);misses=0
            for x,y,label in points:
                xx,yy=int(x-window[0]),int(y-window[1])
                if 0<=yy<mask.shape[0] and 0<=xx<mask.shape[1]:misses+=bool(mask[yy,xx])!=(label==1)
                elif label==1:misses+=1
            return misses,-float(scores[i])
        selected=min(range(len(scores)),key=rank)
        selected_mask=bounded_mask(np.asarray(masks[selected],dtype=bool)&np.asarray(valid,dtype=bool),window,box)
        if anchor is not None:
            from .prompt_components import anchored_mask
            if rank(selected)[0]:raise ValueError('当前模型未找到满足正负点的目标，请调整提示点或框选目标。')
            selected_mask=anchored_mask(selected_mask,window,anchor)
            if selected_mask is None:raise ValueError('预测没有覆盖正点，未采用该结果。请调整正点或框选目标。')
        if single_polygon:
            selected_mask=single_mask(selected_mask,window,points)
        if on_mask:
            mask=selected_mask
            bitmap=preview_bitmap(mask,window,points,single_polygon,max_size=image.get('_preview_size',256))
            on_mask({'mask':bitmap,'window':list(window),'cache_hit':hit,'box':box,'single_polygon':bool(single_polygon)})
        results=[]
        for mask,score,low_mask in [(selected_mask,scores[selected],low[selected])]:
            # SAM 2 returns thresholded masks as float arrays; normalize the
            # public adapter contract before applying the raster validity mask.
            mask = np.asarray(mask, dtype=bool) & np.asarray(valid, dtype=bool)
            geom=clip_geometry(mask_geometry(mask,window,image),box)
            if geom:
                edge=bool((window[0]>0 and mask[:,0].any()) or (window[1]>0 and mask[0].any()) or
                    (window[0]+window[2]<image['width'] and mask[:,-1].any()) or
                    (window[1]+window[3]<image['height'] and mask[-1].any()))
                results.append({'geometry':geom,'score':float(score),'logits':low_mask[None].copy(),'edge':edge,'pixels':int(mask.sum())})
        return {'choices':results,'window':list(window),'cache_hit':hit,'device':self.config['device'],'key':self.cache_key,
                'model_metadata':{'weights_sha256':self.config['weights_sha256'],'adapter':self.schema,'variant':self.config['variant'],'device':self.config['device']}}

