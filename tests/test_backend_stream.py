import numpy as np
from types import SimpleNamespace
from shapely.geometry import box,mapping
from geoforma.backend import SamBackend


def test_native_mask_feedback_precedes_exact_polygonization(monkeypatch):
    import geoforma.backend as backend_module
    backend=SamBackend();backend.encode=lambda *a:True;backend.cache_key='test'
    backend.config={'device':'cpu','weights_sha256':'test','variant':'vit_b'}
    backend.predictor=SimpleNamespace(predict=lambda **kw:(np.ones((1,2,2),bool),np.array([.9]),np.zeros((1,256,256),np.float32)))
    events=[]
    def geometry(*args):events.append('geometry');return mapping(box(0,0,2,2))
    monkeypatch.setattr(backend_module,'mask_geometry',geometry)
    result=backend.predict({'width':2,'height':2},[0,0,2,2],np.zeros((2,2,3),np.uint8),np.ones((2,2),bool),[],on_mask=lambda value:events.append('mask'))
    assert events==['mask','geometry'] and result['choices'][0]['geometry']
