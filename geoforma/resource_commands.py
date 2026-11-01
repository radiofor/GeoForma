"""Headless resource configuration uses the same manager as desktop settings."""
import threading,traceback
from types import SimpleNamespace
from .diagnostics import write_report
from .domain import data_dir

def resource_command(command,output,profile='cpu',files=None,model=None):
    messages=[]
    task=SimpleNamespace(cancel_event=threading.Event(),check=lambda:None,
        signals=SimpleNamespace(progress=SimpleNamespace(emit=lambda current,total,text:messages.append(dict(current=current,total=total,text=text)))))
    try:
        from .native_runtime import NativeRuntimeManager,status
        if command=='status':result=status()
        elif command=='install-runtime':result=NativeRuntimeManager().install(profile,task,files)
        else:
            from .model_catalog import MODELS
            from .weights import install_checkpoint
            spec=next((s for s in MODELS if s['id']==model),None)
            if spec is None:raise ValueError('请选择已登记的模型 ID。')
            if files and len(files)!=1:raise ValueError('模型导入只接受一个权重文件。')
            result=dict(checkpoint=install_checkpoint(spec,task,files[0] if files else None))
        report=dict(ok=True,result=result,progress=messages);code=0
    except Exception:report=dict(ok=False,error=traceback.format_exc(),progress=messages);code=1
    from .resource_location import require_resource_dir
    write_report(output or require_resource_dir()/'runtime/last-resource-command.json',report);return code
