"""Preparation releases transient inputs/features on success, failure and cancel."""
from types import SimpleNamespace
import pytest
from geoforma.inference.engine import ModelEngine
from geoforma.backend import SamBackend
from geoforma.sam2_backend import Sam2Backend


@pytest.mark.parametrize('outcome',['success','failure','cancel'])
def test_preparation_cleans_transients_without_discarding_loaded_weights(outcome):
    engine=ModelEngine();released=[];backend=SimpleNamespace(release_image=lambda:released.append(True));engine.backend=backend
    engine.input_cache=('old','rgb','valid')
    def prepare(*args):
        assert engine.input_cache is None
        engine.input_cache=('new','rgb','valid')
        if outcome!='success':raise RuntimeError(outcome)
        return {'count':1}
    engine._preprocess=prepare
    if outcome=='success':assert engine.preprocess({}, {}, [], None)=={'count':1}
    else:
        with pytest.raises(RuntimeError,match=outcome):engine.preprocess({}, {}, [], None)
    assert released==[True] and engine.input_cache is None and engine.backend is backend


@pytest.mark.parametrize('backend_type,reset_name',[(SamBackend,'reset_image'),(Sam2Backend,'reset_predictor')])
def test_native_cleanup_resets_only_image_features(backend_type,reset_name,monkeypatch):
    import geoforma.backend as module
    monkeypatch.setattr(module.torch.cuda,'is_available',lambda:False)
    backend=backend_type();model=object();backend.model=model;backend.cache_key='encoded';calls=[]
    backend.predictor=SimpleNamespace(**{reset_name:lambda:calls.append(True)})
    backend.release_image();assert calls==[True] and backend.cache_key is None and backend.model is model


