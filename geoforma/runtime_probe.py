"""Validate optional native extensions in a disposable spawn child."""
import multiprocessing,time,traceback
from pathlib import Path

def plain_versions(torch,torchvision):
    # TorchVersion is a str subclass whose pickle would import Torch in the UI.
    return {'torch':str(torch.__version__),'torchvision':str(torchvision.__version__)}

def _check(connection,site,expected):
    try:
        from .process_bootstrap import configure_native_environment,worker_startup_stage
        worker_startup_stage('Initialize runtime verification process')
        configure_native_environment()
        from .native_runtime import activate_path
        activate_path(site)
        connection.send(dict(stage='加载 PyTorch 与 TorchVision',current=0,total=4))
        import torch,torchvision
        connection.send(dict(stage='核对版本与加载目录',current=1,total=4))
        if not Path(torch.__file__).resolve().is_relative_to(Path(site).resolve()):raise ValueError('运行库未从独立目录加载。')
        versions=plain_versions(torch,torchvision)
        if versions!={w['name']:w['version'] for w in expected['wheels']}:raise ValueError('运行库版本不匹配。')
        connection.send(dict(stage='测试 CPU 张量计算',current=2,total=4))
        assert (torch.ones(2,2)@torch.ones(2,2)).sum().item()==8
        connection.send(dict(stage='测试 TorchVision NMS',current=3,total=4))
        answer=torchvision.ops.nms(torch.tensor([[0.,0.,2.,2.]]),torch.tensor([.8]),.5)
        assert answer.tolist()==[0]
        cuda=bool(torch.cuda.is_available())
        if cuda:
            assert (torch.ones(2,2,device='cuda')@torch.ones(2,2,device='cuda')).sum().item()==8
        connection.send(dict(stage='验证完成',current=4,total=4))
        connection.send(dict(ok=True,versions=versions,cuda=cuda))
    except BaseException:connection.send(dict(ok=False,error=traceback.format_exc()))
    finally:connection.close()

def probe(site,spec,task,timeout=180):
    context=multiprocessing.get_context('spawn');parent,child=context.Pipe(False)
    process=context.Process(target=_check,args=(child,str(site),spec),daemon=True,name='GeoFormaRuntimeCheck')
    def child_failure():
        process.join(.2)
        code=process.exitcode
        detail=f'（退出码 {code} / 0x{code & 0xffffffff:08X}）' if code is not None else ''
        return RuntimeError('运行库测试进程异常退出'+detail+'，原配置保留。')
    try:
        process.start();child.close();deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            task.check()
            if parent.poll(.1):
                try:result=parent.recv()
                except EOFError:raise child_failure() from None
                if 'stage' in result:
                    task.signals.progress.emit(result['current'],result['total'],'验证运行库 · '+result['stage']);continue
                if not result['ok']:raise RuntimeError('运行库验证失败，原配置保留。\n'+result['error'])
                return result
            if not process.is_alive():raise child_failure()
        raise RuntimeError('运行库验证超时，原配置保留。')
    finally:
        parent.close();child.close()
        if process.pid is not None:
            process.join(.2)
            if process.is_alive():process.terminate();process.join(5)
            process.close()
