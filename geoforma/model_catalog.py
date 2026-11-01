"""Model definitions shared by UI, downloaders and independent cache adapters."""
import json
from pathlib import Path

_catalog=json.loads(Path(__file__).with_suffix('.json').read_text(encoding='utf-8'))
MODELS=tuple(_catalog['models'])
SAM2_COMMIT=_catalog['sam2_commit']
SAM3_COMMIT=_catalog['sam3_commit']
FAMILIES=('sam','sam2','sam2.1','sam3')


def model_spec(variant,backend='sam'):
    for spec in MODELS:
        if spec['backend']==backend and spec['variant']==variant:return spec
    raise ValueError('此模型版本尚未接入或型号无效。')


def model_title(config):return model_spec(config['variant'],config.get('backend','sam'))['title']


def adapter_schema(backend):
    if backend=='sam':return 'meta_sam_v1_dca509fe_fp32_v1'
    if backend in ('sam2','sam2.1'):return 'meta_'+backend.replace('.','_')+'_'+SAM2_COMMIT[:8]+'_fp32_v1'
    if backend=='sam3':return 'meta_sam3_'+SAM3_COMMIT[:8]+'_interactive_bf16_fp32_cache_v1'
    raise ValueError('此模型版本尚未接入。')


def sam2_descriptor(config,image,window):
    spec=model_spec(config['variant'],config['backend'])
    return {'schema':adapter_schema(config['backend']),'source':image['fingerprint'],
            'grid':[image['width'],image['height'],image['transform']], 'recipe':image['model_recipe'],
            'window':list(window),'weights':config['weights_sha256'],'backend':config['backend'],
            'variant':config['variant'],'config':spec['config'],'code':SAM2_COMMIT,
            'resize':'sam2_square_1024','precision':'float32','postprocessing':False}
