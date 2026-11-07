"""Official SAM 3 interactive predictor with a separate 1008-pixel feature cache."""
import hashlib,os
from pathlib import Path
import torch
from .backend import SamBackend,atomic_torch
from .sam2_backend import Sam2Backend
from .model_catalog import SAM3_COMMIT,adapter_schema,model_spec


class Sam3Backend(Sam2Backend):
    family='sam3'
    cache_bytes=26*1024*1024

    def __init__(self):
        SamBackend.__init__(self)
        self.schema=adapter_schema(self.family);self.image_model=None;self.processor=None

    def load(self,config,on_load=None):
        if config.get('backend')!=self.family:raise ValueError('SAM 3 适配器与模型代际不匹配。')
        spec=model_spec(config['variant'],self.family);path=Path(config['checkpoint'])
        if not path.is_file():raise FileNotFoundError('SAM 3 权重文件不可访问，请重试下载。')
        stamp=(str(path.resolve()),path.stat().st_size,path.stat().st_mtime_ns,config['device'])
        if stamp==self.signature:return
        if on_load:on_load()
        from .sam3_runtime import activate
        activate()
        from sam3.model_builder import build_sam3_image_model
        from sam3.model.sam3_image_processor import Sam3Processor
        with path.open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
        if path.name==spec['file'] and sha!=spec['sha256']:raise ValueError('SAM 3 权重校验失败，请重新下载指定镜像文件。')
        self.close();device=config['device'];fallback=None
        if device=='cuda' and not torch.cuda.is_available():device='cpu'
        if device=='cuda' and not torch.cuda.is_bf16_supported():
            device='cpu';fallback='SAM 3 使用 BF16 推理，当前 GPU 不支持，已回退 CPU。'
        torch.set_num_threads(min(8,os.cpu_count() or 4))
        # Explicit local path and load_from_HF=False prevent any official weight download.
        model=build_sam3_image_model(checkpoint_path=str(path),load_from_HF=False,
                                    enable_inst_interactivity=True,device='cpu',eval_mode=True,compile=False)
        model.requires_grad_(False)
        try:self.image_model=model.to(device)
        except RuntimeError as error:
            if device!='cuda':raise
            fallback=str(error);device='cpu';self.image_model=model.to(device)
            torch.cuda.empty_cache()
        self.predictor=self.image_model.inst_interactive_predictor;self.model=self.predictor.model
        # Morphological postprocessing remains controlled by GeoForma.
        self.predictor._transforms.max_hole_area=0;self.predictor._transforms.max_sprinkle_area=0
        self.processor=Sam3Processor(self.image_model,device=device)
        self.config={**config,'device':device,'weights_sha256':sha,'fallback_reason':fallback};self.signature=stamp

    def descriptor(self,image,window):
        return {'schema':self.schema,'source':image['fingerprint'],
                'grid':[image['width'],image['height'],image['transform']],'recipe':image['model_recipe'],
                'window':list(window),'weights':self.config['weights_sha256'],'backend':self.family,
                'variant':self.config['variant'],'code':SAM3_COMMIT,
                'resize':'sam3_square_1008','precision':'bf16_autocast_fp32_cache','postprocessing':False}

    def restore(self,image,window):
        if not super().restore(image,window):return False
        # The official encoder produces BF16 high-resolution features under
        # autocast. The portable cache stores FP32, so restore their original
        # dtype before decoding to keep the resulting boundary consistent.
        with torch.inference_mode():
            features=self.predictor._features
            features['high_res_feats']=[value.to(dtype=torch.bfloat16) for value in features['high_res_feats']]
        return True

    def encode(self,image,window,rgb=None):
        from .resource_location import require_resource_dir
        if self.restore(image,window):return True
        if rgb is None:
            from .raster import read_rgb
            rgb,_=read_rgb(image,window)
        from PIL import Image
        from .feature_cache import feature_path,check_rewrite_space
        root=require_resource_dir();key=self.key(image,window);path=feature_path(root,key)
        check_rewrite_space(root,path,self.cache_bytes)
        with torch.inference_mode(),torch.autocast(self.config['device'],dtype=torch.bfloat16):
            # PIL preserves H/W correctly; official processor treats arrays as CHW.
            state=self.processor.set_image(Image.fromarray(rgb))
            backbone=state['backbone_out']['sam2_backbone_out'];p=self.predictor
            _,vision,_,_=self.model._prepare_backbone_features(backbone)
            vision[-1]=vision[-1]+self.model.no_mem_embed
            features=[feat.permute(1,2,0).view(1,-1,*size)
                      for feat,size in zip(vision[::-1],p._bb_feat_sizes[::-1])][::-1]
            p._features={'image_embed':features[-1],'high_res_feats':features[:-1]}
            p._orig_hw=[(window[3],window[2])];p._is_image_set=True;p._is_batch=False
            atomic_torch({'key':key,'metadata':self.descriptor(image,window),'source_path':image['path'],
                          'source_crs':image.get('assigned_crs') or image.get('crs',''),
                          'features':{'image_embed':features[-1].float().cpu(),'high_res_feats':[f.float().cpu() for f in features[:-1]]},
                          'orig_hw':[list(p._orig_hw[0])]},path)
        self.cache_key=key;return False

    def predict(self,*args,**kwargs):
        with torch.autocast(self.config['device'],dtype=torch.bfloat16):
            return super().predict(*args,**kwargs)


    def close(self):
        self.processor=None;self.image_model=None
        super().close()
