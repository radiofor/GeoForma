"""Pinned SAM 2/2.1 adapter. Multi-resolution feature state is explicitly isolated."""
import hashlib,os
from pathlib import Path
import torch
from .backend import SamBackend,atomic_torch
from .domain import data_dir
from .model_catalog import model_spec,adapter_schema,sam2_descriptor


class Sam2Backend(SamBackend):
    cache_bytes=20*1024*1024

    def __init__(self,family='sam2'):
        super().__init__();self.family=family;self.schema=adapter_schema(family)

    def load(self,config):
        from sam2.build_sam import build_sam2
        from sam2.sam2_image_predictor import SAM2ImagePredictor
        if config.get('backend')!=self.family:raise ValueError('模型代际与适配器不匹配。')
        spec=model_spec(config['variant'],self.family);path=Path(config['checkpoint'])
        if not path.is_file():raise FileNotFoundError('权重文件不可访问，请重试自动下载。')
        stamp=(str(path.resolve()),path.stat().st_size,path.stat().st_mtime_ns,self.family,config['variant'],config['device'])
        if stamp==self.signature:return
        self.close();device=config['device'];fallback=None
        if device=='cuda' and not torch.cuda.is_available():device='cpu'
        torch.set_num_threads(min(8,os.cpu_count() or 4))
        model=build_sam2(spec['config'],str(path),device='cpu',apply_postprocessing=False)
        model.requires_grad_(False)
        try:self.model=model.eval().to(device)
        except RuntimeError as error:
            if device!='cuda':raise
            fallback=str(error);device='cpu';self.model=model.eval().to(device)
            try:torch.cuda.empty_cache()
            except RuntimeError:pass
        self.predictor=SAM2ImagePredictor(self.model,max_hole_area=0,max_sprinkle_area=0)
        with path.open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
        self.config={**config,'device':device,'weights_sha256':sha,'fallback_reason':fallback};self.signature=stamp

    def descriptor(self,image,window):return sam2_descriptor(self.config,image,window)

    def release_image(self):
        if self.predictor is not None:self.predictor.reset_predictor()
        self.cache_key=None
        if torch.cuda.is_available():torch.cuda.empty_cache()

    def feature_shapes(self):
        p=self.predictor;decoder=self.model.sam_mask_decoder
        return {'image_embed':(1,self.model.hidden_dim,*p._bb_feat_sizes[-1]),
                'high_res_feats':[(1,decoder.conv_s0.out_channels,*p._bb_feat_sizes[0]),
                                  (1,decoder.conv_s1.out_channels,*p._bb_feat_sizes[1])]}

    def restore(self,image,window):
        key=self.key(image,window)
        if key==self.cache_key:return True
        from .feature_cache import feature_path
        from .resource_location import require_resource_dir
        path=feature_path(require_resource_dir(),key)
        if not path.is_file():return False
        try:
            from .feature_cache import load_features
            payload=load_features(path,self.cache_bytes)
            if payload is None:return False
            features=payload['features'];expected=self.feature_shapes()
            if payload.get('key')!=key or payload.get('metadata')!=self.descriptor(image,window) or payload.get('orig_hw')!=[[window[3],window[2]]]:return False
            tensors=[features['image_embed'],*features['high_res_feats']]
            shapes=[expected['image_embed'],*expected['high_res_feats']]
            if len(tensors)!=3 or any(not isinstance(t,torch.Tensor) or tuple(t.shape)!=s or t.dtype!=torch.float32 for t,s in zip(tensors,shapes)):return False
        except Exception:return False
        with torch.inference_mode():
            p=self.predictor;p.reset_predictor();p._features={'image_embed':features['image_embed'].to(self.model.device),
                'high_res_feats':[t.to(self.model.device) for t in features['high_res_feats']]}
            p._orig_hw=[tuple(v) for v in payload['orig_hw']];p._is_image_set=True;p._is_batch=False
        self.cache_key=key;return True

    def encode(self,image,window,rgb=None):
        from .resource_location import require_resource_dir
        if self.restore(image,window):return True
        if rgb is None:
            from .raster import read_rgb
            rgb,_=read_rgb(image,window)
        from .feature_cache import feature_path
        key=self.key(image,window)
        with torch.inference_mode():
            p=self.predictor;p.set_image(rgb)
            features={'image_embed':p._features['image_embed'].cpu(),
                      'high_res_feats':[t.cpu() for t in p._features['high_res_feats']]}
            atomic_torch({'key':key,'metadata':self.descriptor(image,window),'source_path':image['path'],
                          'source_crs':image.get('assigned_crs') or image['crs'],'features':features,
                          'orig_hw':[list(v) for v in p._orig_hw]},feature_path(require_resource_dir(),key))
        self.cache_key=key;return False

