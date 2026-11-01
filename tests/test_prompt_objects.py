"""Different positive objects never become one unconstrained multi-point guess."""
from types import SimpleNamespace
import threading
import numpy as np
import pytest
from shapely.geometry import box,mapping,shape,Point
from geoforma.inference.engine import ModelEngine
from geoforma.prompt_components import anchored_mask
from test_workbench import fake_image


def task():return SimpleNamespace(check=lambda:None,cancel_event=threading.Event(),signals=SimpleNamespace(progress=SimpleNamespace(emit=lambda *args:None),preview=SimpleNamespace(emit=lambda *args:None)))


def test_anchor_component_keeps_holes_and_discards_unprompted_islands():
    mask=np.zeros((20,20),bool);mask[2:8,2:8]=True;mask[4:6,4:6]=False;mask[12:18,12:18]=True
    result=anchored_mask(mask,[100,200,20,20],[103.5,203.5])
    assert result.sum()==32 and not result[5,5] and not result[14,14]
    assert anchored_mask(mask,[100,200,20,20],[110.5,210.5]) is None




def test_prediction_missing_a_positive_is_not_accepted(monkeypatch):
    from geoforma.backend import SamBackend
    backend=SamBackend();backend.encode=lambda *args:True;backend.config=dict(device='cpu',weights_sha256='test',variant='vit_b')
    backend.predictor=SimpleNamespace(predict=lambda **kwargs:(np.ones((3,16,16),bool),np.ones(3),np.zeros((3,256,256),np.float32)))
    # Every candidate violates the negative prompt; don't publish a high score
    # as a successful segmentation when the actual clicks contradict it.
    with pytest.raises(ValueError,match='满足正负点'):
        backend.predict(dict(width=16,height=16,_prompt_anchor=[4,4]),[0,0,16,16],np.zeros((16,16,3),np.uint8),np.ones((16,16),bool),[[4,4,1],[12,12,0]])


