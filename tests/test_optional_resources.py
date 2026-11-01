import hashlib,io,json,threading,zipfile
from pathlib import Path
from types import SimpleNamespace
import pytest
from geoforma import resource_files as files,native_runtime as runtime
from geoforma.tasks import Cancelled

class Task:
    def __init__(self):
        self.messages=[];self.cancel_event=threading.Event();self.signals=SimpleNamespace(progress=SimpleNamespace(emit=lambda *args:self.messages.append(args)))
    def check(self):
        if self.cancel_event.is_set():raise Cancelled()

class Response(io.BytesIO):
    def __init__(self,body,status=200,headers=None):super().__init__(body);self.status=status;self.headers=headers or {}
    def getcode(self):return self.status

def resource(body,name='torch.whl'):return dict(name='torch',filename=name,bytes=len(body),sha256=hashlib.sha256(body).hexdigest(),url='https://download.pytorch.org/test.whl')

def test_local_import_checks_hash_and_keeps_original(tmp_path):
    source=tmp_path/'source.whl';source.write_bytes(b'trusted');spec=resource(b'trusted');task=Task()
    result=files.acquire(spec,tmp_path/'managed',task,source)
    assert result.read_bytes()==source.read_bytes()==b'trusted'
    source.write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='SHA256'):files.acquire(spec,tmp_path/'managed',task,source)
    assert result.read_bytes()==b'trusted'

def test_download_resumes_and_rejects_overlong_response(tmp_path,monkeypatch):
    body=b'abcd1234';spec=resource(body);part=tmp_path/'torch.whl.part';part.write_bytes(body[:3]);requests=[]
    def fetch(request,timeout):
        requests.append(request);return Response(body[3:],206,{'Content-Range':'bytes 3-7/8'})
    monkeypatch.setattr(files,'open_https',fetch)
    assert files.acquire(spec,tmp_path,Task()).read_bytes()==body
    assert requests[0].get_header('Range')=='bytes=3-'
    (tmp_path/'torch.whl').unlink();monkeypatch.setattr(files,'open_https',lambda *a,**k:Response(body+b'extra'))
    with pytest.raises(ValueError,match='超过'):files.acquire(spec,tmp_path,Task())
    assert not (tmp_path/'torch.whl').exists()

def test_corrupt_or_bad_range_download_never_publishes(tmp_path,monkeypatch):
    spec=resource(b'correct');monkeypatch.setattr(files,'open_https',lambda *a,**k:Response(b'corrupt'))
    with pytest.raises(ValueError,match='SHA256'):files.acquire(spec,tmp_path,Task())
    assert not (tmp_path/'torch.whl').exists() and not (tmp_path/'torch.whl.part').exists()
    monkeypatch.setattr(files,'open_https',lambda *a,**k:Response(b'xx',206,{'Content-Range':'bytes 1-2/7'}))
    with pytest.raises(ValueError,match='范围'):files.acquire(spec,tmp_path,Task())

@pytest.mark.parametrize('name',['../escape.dll','/absolute.dll','torch/../../escape.dll','torch\\bad.dll','torch/a:stream','torch/a.','evil.pth','outside/run.py','torch/a.pth'])
def test_wheel_rejects_unsafe_entries(name):
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as archive:
        entry=zipfile.ZipInfo();entry.filename=name;archive.writestr(entry,b'x')
    with zipfile.ZipFile(stream) as archive:
        with pytest.raises(ValueError):runtime.wheel_members(archive)

@pytest.fixture
def install(tmp_path,monkeypatch):
    wheels=[];sources=[]
    for name in ('torch','torchvision'):
        filename=name+'-test.whl';path=tmp_path/filename
        with zipfile.ZipFile(path,'w') as archive:
            archive.writestr(name+'/__init__.py',b'# fixture')
            if name=='torch':archive.writestr('torch/lib/torch_cpu.dll',b'fixture')
        wheels.append(resource(path.read_bytes(),filename)|{'name':name,'version':'test'});sources.append(path)
    spec=dict(title='fixture',wheels=wheels)
    monkeypatch.setattr(runtime,'data_dir',lambda:tmp_path/'app')
    monkeypatch.setattr(runtime,'profile',lambda key:spec)
    monkeypatch.setattr(runtime,'catalog',lambda:dict(profiles={'cpu':spec,'cu126':spec}))
    import geoforma.runtime_probe as probe
    monkeypatch.setattr(probe,'probe',lambda *a:dict(ok=True,versions={'torch':'test','torchvision':'test'}))
    return spec,sources

def test_install_publishes_only_after_validation_and_reuses_configuration(install):
    spec,sources=install;task=Task();manager=runtime.NativeRuntimeManager();first=manager.install('cpu',task,sources)
    assert runtime.managed_runtime()['generation']==first['generation']
    assert not (runtime.runtime_root()/first['generation']/runtime.STAGE_MARKER).exists()
    second=manager.install('cpu',task,sources)
    assert second['generation']==first['generation']
    assert any('运行库 1/2' in text for _,_,text in task.messages)
    assert any('MiB' in text and '安装' in text for _,_,text in task.messages)

def test_failed_reconfiguration_preserves_working_generation(install,monkeypatch):
    _,sources=install;manager=runtime.NativeRuntimeManager();first=manager.install('cpu',Task(),sources)
    import geoforma.runtime_probe as probe
    monkeypatch.setattr(probe,'probe',lambda *a:(_ for _ in ()).throw(RuntimeError('bad extension')))
    with pytest.raises(RuntimeError,match='bad extension'):manager.install('cu126',Task(),sources)
    assert runtime.managed_runtime()['generation']==first['generation']
    assert len([p for p in runtime.runtime_root().iterdir() if p.is_dir() and len(p.name)==32])==1

def test_profile_switch_reuses_verified_install_and_cache_cleanup_preserves_runtime(install):
    _,sources=install;manager=runtime.NativeRuntimeManager();cpu=manager.install('cpu',Task(),sources)
    manager.install('cu126',Task(),sources);again=manager.install('cpu',Task(),sources)
    assert again['generation']==cpu['generation']
    current=runtime.managed_runtime();result=manager.clear_downloads(Task())
    assert result['files']==2 and result['removed_bytes']>0
    assert runtime.managed_runtime()['generation']==current['generation'] and all(p.exists() for p in sources)

def test_small_companion_is_bundled_and_manual_import_needs_only_pytorch(install,monkeypatch):
    _,sources=install
    monkeypatch.setattr(runtime,'bundled_wheel',lambda wheel:sources[1] if wheel['name']=='torchvision' else None)
    assert [wheel['name'] for wheel in runtime.download_wheels('cpu')]==['torch']
    state=runtime.NativeRuntimeManager().install('cpu',Task(),sources[:1])
    assert runtime.managed_runtime()['generation']==state['generation']

def test_cancel_keeps_selected_local_files_and_no_new_active_configuration(install):
    _,sources=install;task=Task();task.cancel_event.set()
    with pytest.raises(Cancelled):runtime.NativeRuntimeManager().install('cpu',task,sources)
    assert all(p.exists() for p in sources) and runtime.managed_runtime() is None

def test_catalog_pins_matching_windows_versions_and_hashes():
    catalog=runtime.catalog();assert catalog['python']=='cp313'
    for key,p in catalog['profiles'].items():
        assert [w['name'] for w in p['wheels']]==['torch','torchvision']
        for w in p['wheels']:
            assert '-cp313-cp313-win_amd64.whl' in w['filename'] and '+'+key in w['filename']
            assert len(w['sha256'])==64 and w['bytes']>0 and w['url'].startswith('https://download-r2.pytorch.org/')

def test_bundle_deduplication_keeps_distinct_binary_versions(tmp_path):
    from geoforma.bundle_layout import deduplicate_binaries
    a=tmp_path/'a.dll';b=tmp_path/'b.dll';c=tmp_path/'c.dll'
    a.write_bytes(b'same');b.write_bytes(b'same');c.write_bytes(b'other')
    toc=[('sample.dll',str(a),'BINARY'),('Library/bin/sample.dll',str(b),'BINARY'),('other/sample.dll',str(c),'BINARY')]
    result=deduplicate_binaries(toc)
    assert len(result)==2 and result[0][0]=='Library/bin/sample.dll' and result[1]==toc[2]

def test_optional_wheel_stdlib_dependencies_are_collected_without_including_torch(tmp_path):
    import sys
    from geoforma.bundle_layout import external_standard_imports
    (tmp_path/'example.py').write_text('import pickletools\nfrom unittest import mock\nimport ctypes.util\nfrom collections.abc import Mapping\nimport torch\nimport tkinter\n',encoding='utf-8')
    name='collections' if sys.version_info>=(3,13) else 'collections.abc'
    assert external_standard_imports([tmp_path])==[name,'ctypes.util','pickletools','unittest']

def test_python_bootstrap_libraries_stay_at_root_before_runtime_hooks(tmp_path):
    from geoforma.bundle_layout import deduplicate_binaries
    path=tmp_path/'runtime.dll';path.write_bytes(b'runtime')
    for name in ('zlib.dll','VCRUNTIME140.dll','api-ms-win-crt-runtime-l1-1-0.dll'):
        entries=[(name,str(path),'BINARY'),('Library/bin/'+name,str(path),'BINARY')]
        assert deduplicate_binaries(entries)==[entries[0]]

def test_runtime_probe_returns_plain_versions_without_torch_types_crossing_ipc():
    from geoforma.runtime_probe import plain_versions
    class TorchVersion(str):pass
    versions=plain_versions(SimpleNamespace(__version__=TorchVersion('2.13.0+cpu')),SimpleNamespace(__version__='0.28.0+cpu'))
    assert versions=={'torch':'2.13.0+cpu','torchvision':'0.28.0+cpu'}
    assert all(type(value) is str for value in versions.values())


def test_runtime_probe_reports_child_exit_when_pipe_closes(monkeypatch):
    import geoforma.runtime_probe as runtime_probe
    class Endpoint:
        def poll(self,timeout):return True
        def recv(self):raise EOFError()
        def close(self):pass
    class Process:
        pid=123
        exitcode=5
        def start(self):pass
        def join(self,timeout):pass
        def is_alive(self):return False
        def close(self):pass
    class Context:
        def Pipe(self,duplex):return Endpoint(),Endpoint()
        def Process(self,**kwargs):return Process()
    monkeypatch.setattr(runtime_probe.multiprocessing,'get_context',lambda mode:Context())
    with pytest.raises(RuntimeError,match='退出码 5 / 0x00000005'):
        runtime_probe.probe('unused',{},Task())
