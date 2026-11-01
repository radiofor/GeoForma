"""Regression checks for cross-generation switching and managed downloads."""
import os,hashlib,io
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtWidgets import QApplication
from geoforma.model_catalog import MODELS,model_spec,adapter_schema
from geoforma.dialogs import ModelDialog
from geoforma.domain import new_project
from types import SimpleNamespace


class Task:
    signals=SimpleNamespace(progress=SimpleNamespace(emit=lambda *args:None))
    def check(self):pass


class Response(io.BytesIO):
    def __init__(self,body):
        super().__init__(body);self.headers={'Content-Length':str(len(body))}
    def getcode(self):return 200


def test_model_popup_has_aligned_fields_and_updates_all_cpu_budgets():
    from geoforma.ui.model_combo import MODEL_COLUMNS_ROLE
    app=QApplication.instance() or QApplication([]);dialog=ModelDialog(new_project()['model'])
    rows=[dialog.variant.itemData(i,MODEL_COLUMNS_ROLE) for i in range(dialog.variant.count())]
    assert rows[0][:2]==['SAM 1','B'] and rows[-1][:2]==['SAM 3','—']
    assert any(row[:2]==['SAM 2.1','Tiny'] for row in rows)
    dialog.device.setCurrentIndex(dialog.device.findData('cpu'))
    assert all(dialog.variant.itemData(i,MODEL_COLUMNS_ROLE)[3]=='CPU' for i in range(dialog.variant.count()))
    dialog.close()


@pytest.mark.parametrize('spec',MODELS,ids=lambda s:s['id'])
def test_selection_preserves_generation_and_uses_correct_weight(spec,tmp_path,monkeypatch):
    import geoforma.weights as weights
    monkeypatch.setattr(weights,'data_dir',lambda:tmp_path)
    app=QApplication.instance() or QApplication([])
    dialog=ModelDialog(new_project()['model'])
    dialog.variant.setCurrentIndex(dialog.variant.findData(spec['id']))
    chosen=dialog.value()
    assert chosen['backend']==spec['backend'] and chosen['variant']==spec['variant']
    assert chosen['checkpoint'].endswith(spec['file'])
    reopened=ModelDialog(chosen)
    assert reopened.selected_spec()['id']==spec['id']
    dialog.close();reopened.close()


@pytest.mark.parametrize('family',['sam2','sam2.1'])
def test_missing_sam2_weight_uses_official_source_and_validates(family,tmp_path,monkeypatch):
    import torch
    import geoforma.weights as weights
    spec=dict(model_spec('tiny',family));stream=io.BytesIO()
    torch.save({'model':{k:torch.empty((1,),device='meta') for k in [
        'image_encoder.trunk.patch_embed.proj.weight','sam_prompt_encoder.point_embeddings.0.weight',
        'sam_mask_decoder.iou_token.weight']}},stream)
    body=stream.getvalue();spec['sha256']=hashlib.sha256(body).hexdigest();requests=[]
    monkeypatch.setattr(weights,'model_spec',lambda variant,backend='sam':spec)
    monkeypatch.setattr(weights,'data_dir',lambda:tmp_path)
    def fetch(request,timeout):requests.append(request.full_url);return Response(body)
    monkeypatch.setattr(weights,'urlopen',fetch)
    # A stale official SAM 1 path must not load a different generation's weights.
    stale=tmp_path/'sam_vit_l_0b3195.pth';stale.write_bytes(b'wrong generation')
    path=weights.ensure_checkpoint({'backend':family,'variant':'tiny','checkpoint':str(stale)},Task())
    assert requests==[spec['url']] and stale.read_bytes()==b'wrong generation'
    assert __import__('pathlib').Path(path).read_bytes()==body


def test_generation_switch_cannot_share_cache_identity():
    from geoforma.model_catalog import sam2_descriptor
    image={'fingerprint':'source','width':2048,'height':1024,'transform':[1,0,0,0,-1,0],
           'model_recipe':{'bands':[1,2,3]}}
    first=sam2_descriptor({'backend':'sam2','variant':'small','weights_sha256':'hash'},image,[0,0,1024,1024])
    second=sam2_descriptor({'backend':'sam2.1','variant':'small','weights_sha256':'hash'},image,[0,0,1024,1024])
    assert first!=second and adapter_schema('sam')!=first['schema']!=second['schema']
    with pytest.raises(ValueError):model_spec('tiny','sam3')
