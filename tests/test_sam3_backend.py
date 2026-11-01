from types import SimpleNamespace
import io,hashlib
import numpy as np
import torch
from shapely.geometry import box,mapping
from geoforma.model_catalog import model_spec,adapter_schema
from geoforma.sam3_backend import Sam3Backend
from geoforma.backend import SamBackend


def test_sam3_uses_requested_mirror_and_safe_weight_validation(tmp_path,monkeypatch):
    import geoforma.weights as weights
    spec=dict(model_spec('interactive','sam3'));assert spec['url'].startswith('https://huggingface.co/1038lab/sam3/')
    stream=io.BytesIO();torch.save({key:torch.ones(1) for key in ['detector.backbone.test','tracker.sam_prompt_encoder.point_embeddings.0.weight','tracker.sam_mask_decoder.iou_token.weight']},stream)
    body=stream.getvalue();spec.update(sha256=hashlib.sha256(body).hexdigest(),bytes=len(body));urls=[]
    class Response(io.BytesIO):
        headers={'Content-Length':str(len(body))}
        def getcode(self):return 200
    def fetch(request,timeout):urls.append(request.full_url);return Response(body)
    monkeypatch.setattr(weights,'model_spec',lambda *a:spec);monkeypatch.setattr(weights,'data_dir',lambda:tmp_path);monkeypatch.setattr(weights,'urlopen',fetch)
    task=SimpleNamespace(check=lambda:None,signals=SimpleNamespace(progress=SimpleNamespace(emit=lambda *a:None)))
    result=weights.ensure_checkpoint({'backend':'sam3','variant':'interactive'},task)
    assert urls==[spec['url']] and result.endswith('sam3.pt')


def test_sam3_cache_preserves_official_feature_dimensions(tmp_path,monkeypatch):
    import geoforma.sam3_backend as module
    import geoforma.sam2_backend as base
    monkeypatch.setattr(module,'data_dir',lambda:tmp_path);monkeypatch.setattr(base,'data_dir',lambda:tmp_path)
    backend=Sam3Backend();backend.config={'variant':'interactive','weights_sha256':'test','device':'cpu'}
    sizes=[(4,4),(2,2),(1,1)];calls=[]
    model=SimpleNamespace(hidden_dim=2,device='cpu',no_mem_embed=torch.zeros((1,1,2)),
        sam_mask_decoder=SimpleNamespace(conv_s0=SimpleNamespace(out_channels=2),conv_s1=SimpleNamespace(out_channels=2)),
        _prepare_backbone_features=lambda state:(None,[torch.ones(h*w,1,2) for h,w in sizes],None,None))
    backend.model=model
    predictor=SimpleNamespace(_bb_feat_sizes=sizes,reset_predictor=lambda:None)
    backend.predictor=predictor
    def set_image(image):calls.append(image.size);return {'backbone_out':{'sam2_backbone_out':{}}}
    backend.processor=SimpleNamespace(set_image=set_image)
    image={'fingerprint':'test','width':16,'height':8,'transform':[1,0,0,0,-1,0],'model_recipe':{'bands':[1,2,3]},'path':'test.tif','crs':''}
    assert not backend.encode(image,[0,0,16,8],np.zeros((8,16,3),np.uint8))
    assert calls==[(16,8)] and predictor._orig_hw==[(8,16)]
    backend.cache_key=None;predictor._features=None
    assert backend.restore(image,[0,0,16,8])
    assert tuple(predictor._features['image_embed'].shape)==(1,2,1,1)
    assert all(value.dtype==torch.bfloat16 for value in predictor._features['high_res_feats'])
    assert backend.descriptor(image,[0,0,16,8])['resize']=='sam3_square_1008'
    assert backend.schema!=adapter_schema('sam2.1')


def test_seed_mask_uses_predictors_actual_size(monkeypatch):
    backend=SamBackend();backend.encode=lambda *a:True;backend.cache_key='test'
    backend.config={'device':'cpu','weights_sha256':'test','variant':'interactive'};captured=[]
    def predict(**kwargs):
        captured.append(kwargs['mask_input'].shape)
        return np.ones((1,4,4),bool),np.array([.9]),np.zeros((1,288,288),np.float32)
    backend.predictor=SimpleNamespace(model=SimpleNamespace(sam_prompt_encoder=SimpleNamespace(mask_input_size=(288,288))),predict=predict)
    backend.predict({'width':4,'height':4},[0,0,4,4],np.zeros((4,4,3),np.uint8),np.ones((4,4),bool),[],seed=mapping(box(0,0,4,4)))
    assert captured==[(1,288,288)]
