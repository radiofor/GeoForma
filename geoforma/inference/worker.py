"""Windows spawn entry point; the child alone imports the inference engine."""


class _ParentDisconnected(Exception):pass


def _pipe_disconnected(error):
    return isinstance(error,(BrokenPipeError,EOFError,ConnectionResetError)) or getattr(error,'winerror',None) in (109,232,233)


def _model_process(connection,cancel_event):
    """Only this spawn process imports torch. SAM runs on its main Python thread."""
    import traceback
    from ..process_bootstrap import configure_native_environment,worker_startup_stage
    def send(message):
        try:connection.send(message)
        except (OSError,EOFError) as error:
            if _pipe_disconnected(error):raise _ParentDisconnected from None
            raise
    class Progress:
        def emit(self,current,total,message):send(('progress',(current,total,message)))
    class Signals:pass
    class Preview:
        def emit(self,value):send(('preview',value))
    class ProcessTask:
        def __init__(self):
            self.cancel_event=cancel_event;self.signals=Signals();self.signals.progress=Progress();self.signals.preview=Preview()
        def check(self):
            if self.cancel_event.is_set():raise RuntimeError('任务已取消；已完成缓存保留。')
    engine=None
    try:
        if cancel_event.is_set():return
        stage='初始化原生运行环境'
        try:
            worker_startup_stage(stage)
            configure_native_environment()
            if cancel_event.is_set():return
            stage='激活 PyTorch 运行库';worker_startup_stage(stage)
            from ..native_runtime import activate
            activate()
            stage='加载模型引擎';worker_startup_stage(stage)
            from .engine import ModelEngine
            engine=ModelEngine()
        except BaseException:
            diagnostic=f'模型进程初始化失败（{stage}）。\n'+traceback.format_exc()
            worker_startup_stage(diagnostic)
            send(('startup_error',diagnostic))
            return
        if cancel_event.is_set():return
        worker_startup_stage('Model worker ready')
        send(('ready',None))
        while True:
            try:command=connection.recv()
            except (OSError,EOFError) as error:
                if _pipe_disconnected(error):break
                raise
            if command is None:break
            method,args=command
            try:
                if method not in ('prepare_model','preprocess','predict','preview'):raise ValueError('Unsupported model operation')
                result=getattr(engine,method)(*args,ProcessTask())
                if isinstance(result,dict) and engine.backend is not None:result['execution']=getattr(engine.backend,'execution','native')
                send(('result',result))
            except _ParentDisconnected:raise
            except Exception:send(('error',traceback.format_exc()))
    except _ParentDisconnected:
        # Exit/cancel can close the parent's endpoint during initialization or
        # any reply. There is no receiver left to report an exception to.
        pass
    finally:
        try:
            if engine is not None:engine.close()
        finally:connection.close()
