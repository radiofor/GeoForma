"""Only actual model reloads should be announced as model loading."""
import pytest


@pytest.mark.parametrize('family,variant', [('sam','vit_b'),('sam2','small'),('sam2.1','small'),('sam3','interactive')])
def test_adapter_reports_only_when_model_needs_loading(tmp_path,family,variant):
    from geoforma.backend_factory import native_backend
    path=tmp_path/'weights.pth';path.write_bytes(b'weights')
    backend=native_backend(family)
    config={'backend':family,'variant':variant,'checkpoint':str(path),'device':'cpu'}
    info=path.stat();prefix=(str(path.resolve()),info.st_size,info.st_mtime_ns)
    backend.signature=prefix+((variant,'cpu') if family=='sam' else ('cpu',) if family=='sam3' else (family,variant,'cpu'))
    events=[]
    backend.load(config,on_load=lambda:events.append('loading'))
    assert events==[]
    backend.signature=None
    def before_load():
        events.append('loading')
        raise RuntimeError('test stopped before loading')
    with pytest.raises(RuntimeError,match='test stopped before loading'):
        backend.load(config,on_load=before_load)
    assert events==['loading']


def test_engine_reports_reload_and_checks_cancellation(monkeypatch):
    from types import SimpleNamespace
    from geoforma.inference.engine import ModelEngine
    from geoforma import weights,execution_policy,backend_factory
    events=[]
    class Backend:
        execution='native';family='sam'
        config={'device':'cpu'}
        def __init__(self):self.loaded=False
        def load(self,config,on_load=None):
            if not self.loaded:
                on_load();self.loaded=True
    backend=Backend();engine=ModelEngine()
    monkeypatch.setattr(weights,'ensure_checkpoint',lambda config,task:'weights')
    monkeypatch.setattr(execution_policy,'resolve_execution',lambda config:'native')
    monkeypatch.setattr(backend_factory,'create_backend',lambda config:backend)
    task=SimpleNamespace(check=lambda:None,signals=SimpleNamespace(progress=SimpleNamespace(emit=lambda *args:events.append(args))))
    config={'backend':'sam','checkpoint':'weights'}
    engine.prepare_model(config,task);engine.prepare_model(config,task)
    assert events==[(0,0,'加载 SAM 模型…')]
    backend.loaded=False;checks=[];events.clear()
    def check():
        checks.append(1)
        if len(checks)==2:raise RuntimeError('cancelled')
    task.check=check
    with pytest.raises(RuntimeError,match='cancelled'):engine.prepare_model(config,task)
    assert events==[] and not backend.loaded
