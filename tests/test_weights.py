import hashlib,io,json,threading
from types import SimpleNamespace
import pytest
import torch
from geoforma import weights
from geoforma.tasks import Cancelled


class Response(io.BytesIO):
    def __init__(self,body,status=200,headers=None):
        super().__init__(body);self.status=status;self.headers={'Content-Length':str(len(body)),'ETag':'test',**(headers or {})}
    def getcode(self):return self.status


class Task:
    def __init__(self,cancel_on_progress=False):
        self.cancel_event=threading.Event();self.messages=[];self.cancel_on_progress=cancel_on_progress
        self.signals=SimpleNamespace(progress=SimpleNamespace(emit=self.progress))
    def progress(self,current,total,message):
        self.messages.append(message)
        if self.cancel_on_progress and message.startswith('下载权重 · SAM '):self.cancel_event.set()
    def check(self):
        if self.cancel_event.is_set():raise Cancelled()


@pytest.fixture
def download(tmp_path,monkeypatch):
    stream=io.BytesIO();torch.save({'image_encoder.patch_embed.proj.weight':torch.empty((768,3,16,16),device='meta'),
        'prompt_encoder.point_embeddings.0.weight':torch.empty((1,256),device='meta'),
        'mask_decoder.iou_token.weight':torch.empty((1,256),device='meta'),'padding':torch.zeros(3*1024*1024,dtype=torch.uint8)},stream)
    body=stream.getvalue();requests=[]
    monkeypatch.setattr(weights,'data_dir',lambda:tmp_path)
    monkeypatch.setattr(weights,'KNOWN_SHA256',{'vit_b':hashlib.sha256(body).hexdigest()})
    def fetch(request,timeout):
        requests.append(request);range_header=request.get_header('Range')
        if range_header:
            offset=int(range_header.split('=')[1].split('-')[0])
            return Response(body[offset:],206,{'Content-Range':f'bytes {offset}-{len(body)-1}/{len(body)}'})
        return Response(body)
    monkeypatch.setattr(weights,'urlopen',fetch)
    config={'variant':'vit_b','checkpoint':str(tmp_path/'missing_custom_path.pth')}
    return config,body,requests


def test_missing_file_downloads_validates_and_reuses(download):
    config,body,requests=download;target=weights.ensure_checkpoint(config,Task())
    from pathlib import Path
    assert Path(target).read_bytes()==body and len(requests)==1
    assert weights.ensure_checkpoint(config,Task())==target and len(requests)==1
    assert not Path(target+'.part').exists()


def test_cancel_preserves_partial_and_resume_uses_range(download):
    config,body,requests=download
    with pytest.raises(Cancelled):weights.ensure_checkpoint(config,Task(True))
    target=weights.default_checkpoint('vit_b');part=target.with_suffix('.pth.part');offset=part.stat().st_size
    assert 0<offset<len(body) and not target.exists()
    assert weights.ensure_checkpoint(config,Task())==str(target)
    assert requests[-1].get_header('Range')==f'bytes={offset}-' and target.read_bytes()==body


def test_server_ignoring_range_restarts_without_appending(download,monkeypatch):
    config,body,requests=download
    with pytest.raises(Cancelled):weights.ensure_checkpoint(config,Task(True))
    monkeypatch.setattr(weights,'urlopen',lambda *a,**k:Response(body))
    path=weights.ensure_checkpoint(config,Task());from pathlib import Path
    assert Path(path).read_bytes()==body


def test_bad_checksum_never_publishes_target(download,monkeypatch):
    config,_,_=download;monkeypatch.setattr(weights,'KNOWN_SHA256',{'vit_b':'wrong'})
    with pytest.raises(ValueError,match='SHA256'):weights.ensure_checkpoint(config,Task())
    target=weights.default_checkpoint('vit_b');assert not target.exists();assert target.with_name(target.name+'.part.invalid').exists()


def test_existing_custom_path_does_not_download(download,tmp_path):
    config,_,requests=download;custom=tmp_path/'offline.pth';custom.write_bytes(b'existing custom file')
    config['checkpoint']=str(custom);assert weights.ensure_checkpoint(config,Task())==str(custom) and not requests


def test_html_error_is_not_saved_as_model(download,monkeypatch):
    config,_,_=download;monkeypatch.setattr(weights,'urlopen',lambda *a,**k:Response(b'<html>error</html>',headers={'Content-Type':'text/html'}))
    with pytest.raises(ValueError,match='网页'):weights.ensure_checkpoint(config,Task())
    assert not weights.default_checkpoint('vit_b').exists()
