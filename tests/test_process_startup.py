"""Source-only regressions for frozen worker initialization and IPC failures."""
import builtins
from collections import deque
import runpy
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from geoforma import native_runtime,process_bootstrap,runtime_probe,runtime_profile
from geoforma.inference import worker
from geoforma.inference.client import ModelService


def test_native_initialization_pins_codecs_before_optional_libraries(monkeypatch):
    from environment import _geoforma_runtime
    events=[];original=builtins.__import__
    monkeypatch.setattr(runtime_profile,'activate_security_profile',lambda:events.append('profile'))
    monkeypatch.setattr(_geoforma_runtime,'configure',lambda:events.append('dll-paths'))
    monkeypatch.setenv('GDAL_VRT_ENABLE_PYTHON','YES')
    def guarded_import(name,*args,**kwargs):
        if name=='PIL':
            import os
            assert os.environ['GDAL_VRT_ENABLE_PYTHON']=='NO'
            events.append('pillow');return SimpleNamespace(Image=object())
        assert name.split('.')[0] not in ('torch','torchvision','PySide6','rasterio')
        return original(name,*args,**kwargs)
    monkeypatch.setattr(builtins,'__import__',guarded_import)
    process_bootstrap.configure_native_environment()
    assert events==['profile','dll-paths','pillow']


def worker_fixture(monkeypatch,commands):
    events=[];messages=[];commands=deque(commands)
    monkeypatch.setattr(process_bootstrap,'configure_native_environment',lambda:events.append('environment'))
    monkeypatch.setattr(native_runtime,'activate',lambda:events.append('activate'))
    backend=SimpleNamespace(backend=None,close=lambda:events.append('engine-close'),
                            prepare_model=lambda *args:{'ok':True})
    def create_engine():events.append('engine');return backend
    monkeypatch.setitem(sys.modules,'geoforma.inference.engine',SimpleNamespace(ModelEngine=create_engine))
    connection=SimpleNamespace(recv=lambda:commands.popleft(),send=messages.append,
                               close=lambda:events.append('pipe-close'))
    return events,messages,backend,connection


def test_model_worker_initializes_before_ready_and_releases_resources(monkeypatch):
    events,messages,_,connection=worker_fixture(monkeypatch,[('prepare_model',({},)),None])
    worker._model_process(connection,threading.Event())
    assert events==['environment','activate','engine','engine-close','pipe-close']
    assert messages==[('ready',None),('result',{'ok':True})]


@pytest.mark.parametrize('failure',['environment','activate','engine-import','engine'])
def test_model_worker_reports_all_initialization_failures(monkeypatch,failure):
    events,messages,_,connection=worker_fixture(monkeypatch,[])
    def fail():raise OSError('fixture DLL unavailable')
    if failure=='environment':monkeypatch.setattr(process_bootstrap,'configure_native_environment',fail)
    elif failure=='activate':monkeypatch.setattr(native_runtime,'activate',fail)
    elif failure=='engine-import':
        original=builtins.__import__
        def importing(name,*args,**kwargs):
            if name=='engine':raise ImportError('fixture DLL unavailable')
            return original(name,*args,**kwargs)
        monkeypatch.setattr(builtins,'__import__',importing)
    else:monkeypatch.setitem(sys.modules,'geoforma.inference.engine',SimpleNamespace(ModelEngine=fail))
    worker._model_process(connection,threading.Event())
    assert len(messages)==1 and messages[0][0]=='startup_error'
    assert 'fixture DLL unavailable' in messages[0][1] and 'Traceback' in messages[0][1]
    assert events[-1]=='pipe-close' and 'engine-close' not in events


def test_model_operation_error_keeps_worker_available_for_retry(monkeypatch):
    _,messages,backend,connection=worker_fixture(monkeypatch,[('invalid',()),('prepare_model',({},)),None])
    worker._model_process(connection,threading.Event())
    assert [kind for kind,_ in messages]==['ready','error','result']
    assert 'Unsupported model operation' in messages[1][1] and messages[2][1]=={'ok':True}


@pytest.mark.parametrize('phase',['ready','progress','preview','result','error','startup_error','receive'])
@pytest.mark.parametrize('failure',['broken-pipe','eof',109,232,233])
def test_worker_parent_disconnect_exits_cleanly_without_secondary_reply(monkeypatch,phase,failure):
    events,messages,backend,connection=worker_fixture(monkeypatch,[('prepare_model',({},)),None])
    if failure=='broken-pipe':error=BrokenPipeError('parent closed')
    elif failure=='eof':error=EOFError('parent closed')
    else:
        error=OSError('parent closed');error.winerror=failure
    attempts=[]
    def fail():raise error
    def send(message):
        attempts.append(message[0])
        if message[0]==phase:fail()
        messages.append(message)
    connection.send=send
    if phase=='receive':connection.recv=fail
    elif phase=='startup_error':
        def startup_failure():raise ImportError('model initialization failed')
        monkeypatch.setattr(native_runtime,'activate',startup_failure)
    elif phase=='error':
        def operation_failure(*args):raise ValueError('model operation failed')
        backend.prepare_model=operation_failure
    elif phase in ('progress','preview'):
        def operation(*args):
            task=args[-1]
            if phase=='progress':task.signals.progress.emit(1,2,'preparing')
            else:task.signals.preview.emit({'preview':True})
            pytest.fail('operation continued after parent disconnect')
        backend.prepare_model=operation
    worker._model_process(connection,threading.Event())
    assert events[-1]=='pipe-close'
    assert events.count('engine-close')==(0 if phase=='startup_error' else 1)
    assert attempts==(['ready'] if phase in ('ready','receive') else ['startup_error'] if phase=='startup_error' else ['ready',phase])


def test_worker_unrelated_pipe_error_remains_visible(monkeypatch):
    events,_,_,connection=worker_fixture(monkeypatch,[])
    error=OSError('access denied');error.winerror=5
    def send(message):raise error
    connection.send=send
    with pytest.raises(OSError,match='access denied'):worker._model_process(connection,threading.Event())
    assert events[-2:]==['engine-close','pipe-close']


@pytest.mark.parametrize('phase',['before-start','environment','engine'])
def test_worker_cancelled_initialization_does_not_send_ready(monkeypatch,phase):
    events,messages,backend,connection=worker_fixture(monkeypatch,[])
    cancelled=threading.Event()
    if phase=='before-start':cancelled.set()
    elif phase=='environment':
        def configure():events.append('environment');cancelled.set()
        monkeypatch.setattr(process_bootstrap,'configure_native_environment',configure)
    else:
        def create_engine():events.append('engine');cancelled.set();return backend
        monkeypatch.setitem(sys.modules,'geoforma.inference.engine',SimpleNamespace(ModelEngine=create_engine))
    worker._model_process(connection,cancelled)
    assert messages==[] and events[-1]=='pipe-close'
    assert events.count('engine-close')==(1 if phase=='engine' else 0)
    if phase=='before-start':assert events==['pipe-close']


def test_worker_closed_real_pipe_during_ready_releases_engine(monkeypatch):
    import multiprocessing
    events,_,_,_=worker_fixture(monkeypatch,[])
    parent,child=multiprocessing.Pipe();parent.close()
    worker._model_process(child,threading.Event())
    assert events[-1]=='engine-close' and child.closed


def test_runtime_probe_initialization_failure_is_reported_without_torch(monkeypatch):
    messages=[];closed=[]
    def fail():raise OSError('fixture codec unavailable')
    monkeypatch.setattr(process_bootstrap,'configure_native_environment',fail)
    monkeypatch.setattr(native_runtime,'activate_path',lambda *a:pytest.fail('runtime activated before bundled codecs'))
    connection=SimpleNamespace(send=messages.append,close=lambda:closed.append(True))
    runtime_probe._check(connection,'unused',{})
    assert closed==[True] and messages[0]['ok'] is False
    assert 'fixture codec unavailable' in messages[0]['error']


def test_frozen_hook_captures_diagnostics_before_path_initialization(monkeypatch):
    from environment import _geoforma_runtime
    events=[]
    monkeypatch.setattr(process_bootstrap,'configure_worker_diagnostics',lambda:events.append('diagnostics'))
    monkeypatch.setattr(process_bootstrap,'worker_startup_stage',lambda text:events.append('stage'))
    monkeypatch.setattr(_geoforma_runtime,'configure',lambda:events.append('paths'))
    runpy.run_path(str(Path(__file__).resolve().parents[1]/'packaging/runtime_hook.py'))
    assert events==['diagnostics','stage','paths']


def test_frozen_diagnostics_are_idempotent_and_record_stages(tmp_path,monkeypatch):
    import faulthandler
    from geoforma import domain
    monkeypatch.setattr(sys,'frozen',True,raising=False)
    monkeypatch.setattr(sys,'argv',['GeoForma.exe','--multiprocessing-fork','parent_pid=123','pipe_handle=456'])
    monkeypatch.setattr(sys,'stderr',None);monkeypatch.setattr(sys,'stdout',None)
    monkeypatch.setattr(domain,'data_dir',lambda:tmp_path)
    monkeypatch.setenv('GEOFORMA_DATA_DIR',str(tmp_path))
    monkeypatch.setattr(process_bootstrap,'_worker_log',None)
    enabled=[];monkeypatch.setattr(faulthandler,'enable',lambda **kw:enabled.append(kw['file']))
    try:
        process_bootstrap.configure_worker_diagnostics();first=sys.stderr
        process_bootstrap.configure_worker_diagnostics()
        process_bootstrap.worker_startup_stage('fixture engine import')
        assert sys.stderr is first and sys.stdout is first and enabled==[first]
        text=(tmp_path/'worker-startup.log').read_text(encoding='utf-8')
        assert 'Python worker entry' in text and 'fixture engine import' in text
    finally:
        if process_bootstrap._worker_log is not None:process_bootstrap._worker_log.close()


def client_fixture(monkeypatch,replies):
    events=[];queue=deque(replies);service=ModelService()
    process=SimpleNamespace(exitcode=None,alive=True)
    process.is_alive=lambda:process.alive
    process.join=lambda **kw:events.append('join')
    def terminate():process.alive=False;events.append('terminate')
    process.terminate=terminate;process.close=lambda:events.append('process-close')
    def send(message):
        events.append(('send',message))
        if message is None:process.alive=False
    def receive():
        item=queue.popleft();events.append(('receive',item[0]))
        if isinstance(item[1],BaseException):raise item[1]
        return item
    connection=SimpleNamespace(send=send,recv=receive,poll=lambda timeout:bool(queue),
                               close=lambda:events.append('pipe-close'))
    service.process=process;service.connection=connection;service.cancel_event=threading.Event()
    monkeypatch.setattr(service,'_start',lambda:None)
    progress=[];task=SimpleNamespace(cancel_event=threading.Event(),signals=SimpleNamespace(progress=SimpleNamespace(emit=lambda *a:progress.append(a))))
    return service,task,process,queue,events


def test_client_waits_for_ready_and_reuses_initialized_worker(monkeypatch):
    service,task,_,queue,events=client_fixture(monkeypatch,[('ready',None),('result',1)])
    assert service.prepare_model({},task)==1
    assert events.index(('receive','ready'))<events.index(('send',('prepare_model',({},))))
    queue.append(('result',2))
    assert service.prepare_model({},task)==2 and service.ready
    service.close()
    assert not service.ready and service.cancel_event is None


def test_client_startup_error_never_sends_operation_and_closes_worker(monkeypatch):
    service,task,_,_,events=client_fixture(monkeypatch,[('startup_error','fixture DLL unavailable')])
    with pytest.raises(RuntimeError,match='fixture DLL unavailable'):service.prepare_model({},task)
    assert not any(item==('send',('prepare_model',({},))) for item in events)
    assert 'pipe-close' in events and 'process-close' in events
    assert service.process is service.connection is service.cancel_event is None and not service.ready


def test_client_operation_failure_can_retry_with_progress_and_preview(monkeypatch):
    service,task,_,queue,_=client_fixture(monkeypatch,[('ready',None),('error','fixture invalid prompt')])
    with pytest.raises(RuntimeError,match='invalid prompt'):service.prepare_model({},task)
    previews=[];task.signals.preview=SimpleNamespace(emit=previews.append)
    queue.extend([('progress',(1,2,'fixture progress')),('preview','fixture bitmap'),('result',{'ok':True})])
    assert service.prepare_model({},task)=={'ok':True}
    assert previews==['fixture bitmap'] and service.ready
    service.close()


def test_client_rejects_unexpected_handshake_and_closes_worker(monkeypatch):
    service,task,_,_,events=client_fixture(monkeypatch,[('result','premature result')])
    with pytest.raises(RuntimeError,match='启动响应无效'):service.prepare_model({},task)
    assert 'pipe-close' in events and 'process-close' in events and not service.ready


def test_client_handles_native_exit_without_demanding_cpu_switch(monkeypatch):
    service,task,process,_,events=client_fixture(monkeypatch,[])
    process.alive=False;process.exitcode=4294967295
    with pytest.raises(RuntimeError,match='0xFFFFFFFF') as caught:service.prepare_model({},task)
    assert 'CPU' not in str(caught.value) and 'process-close' in events


def test_client_eof_during_initialization_releases_handles(monkeypatch):
    service,task,_,_,events=client_fixture(monkeypatch,[('eof',EOFError())])
    with pytest.raises(RuntimeError,match='启动中断'):service.prepare_model({},task)
    assert 'pipe-close' in events and 'process-close' in events


def test_client_can_stop_initialization_before_a_command_is_sent(monkeypatch):
    service,task,_,_,events=client_fixture(monkeypatch,[]);task.cancel_event.set()
    with pytest.raises(RuntimeError,match='已停止'):service.prepare_model({},task)
    assert ('send',('prepare_model',({},))) not in events and 'process-close' in events


def test_client_initialization_timeout_does_not_leave_a_worker(monkeypatch):
    from geoforma.inference import client
    service,task,_,_,events=client_fixture(monkeypatch,[])
    times=iter([0,181]);monkeypatch.setattr(client.time,'monotonic',lambda:next(times))
    with pytest.raises(RuntimeError,match='初始化超时'):service.prepare_model({},task)
    assert 'pipe-close' in events and 'process-close' in events
