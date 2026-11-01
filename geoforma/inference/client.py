"""Persistent model-process client. No heavy model or raster imports."""
import time


class ModelService:
    """Serialized IPC facade; one persistent GPU owner, no Qt objects cross IPC."""
    def __init__(self):
        self.process=None;self.connection=None;self.cancel_event=None;self.ready=False;self.cancel_requested_at=None
        self.cache_owner=None;self.cache_generation=0;self.cache_changed=False;self.cache_revision=None

    def activate_project(self,root,owner):
        """Called in the serialized task thread before any model/cache writer."""
        from pathlib import Path
        from ..project_cache import activate_project_cache
        identity=(str(Path(root).resolve()),owner)
        self.cache_changed=False
        if identity==self.cache_owner:return False
        # Stop the old writer and release decoded tensors before deleting files.
        self.close()
        result=activate_project_cache(root,owner)
        self.cache_owner=identity;self.cache_revision=result['revision']
        self.cache_changed=result['cleared']
        if result['cleared'] and result['removed']:self.cache_generation+=1
        return result['cleared']

    def _start(self):
        import multiprocessing
        from .worker import _model_process
        if self.process is not None and self.process.is_alive():return
        self.close();context=multiprocessing.get_context('spawn');parent,child=context.Pipe();self.cancel_event=context.Event()
        process=context.Process(target=_model_process,args=(child,self.cancel_event),name='GeoForma',daemon=True)
        try:process.start()
        except BaseException:
            parent.close();self.cancel_event=None
            if process.pid is None:process.close()
            raise
        finally:child.close()
        self.process=process;self.connection=parent

    def _call(self,method,args,task):
        try:return self._exchange(method,args,task)
        except (OSError,EOFError) as error:
            code=self.process.exitcode if self.process is not None else None
            message=self._exit_message(code)
            self.close()
            raise RuntimeError(message+('\n'+str(error) if str(error) else '')) from None

    def _exit_message(self,code):
        import sys
        state='运行' if self.ready else '启动'
        detail=f'（退出码 {code} / 0x{code & 0xFFFFFFFF:08X}）' if code is not None else ''
        hint=' 启动日志：worker-startup.log。' if getattr(sys,'frozen',False) else ''
        return f'模型进程{state}中断{detail}，请重试。已保存标签保留。'+hint

    def _receive(self,task,deadline=None):
        while True:
            if task.cancel_event.is_set():
                self.cancel_event.set()
                if not self.ready:
                    self.close();raise RuntimeError('模型进程启动已停止。')
                if self.cancel_requested_at is None:self.cancel_requested_at=time.monotonic()
                elif time.monotonic()-self.cancel_requested_at>=5:
                    # Native operations may not check the shared cancellation event.
                    self.close();raise RuntimeError('操作已取消，未响应的模型进程已释放。')
            if deadline is not None and time.monotonic()>=deadline:
                self.close();raise RuntimeError('模型进程初始化超时，请重试。')
            if self.connection.poll(.05):
                return self.connection.recv()
            elif not self.process.is_alive():
                message=self._exit_message(self.process.exitcode);self.close()
                raise RuntimeError(message)

    def _exchange(self,method,args,task):
        self._start();self.cancel_event.clear();self.cancel_requested_at=None
        if not self.ready:
            task.signals.progress.emit(0,0,'初始化模型进程…')
            # Wait for native initialization before sending an operation. A
            # failed worker can report its startup error without a send race.
            kind,value=self._receive(task,time.monotonic()+180)
            if kind!='ready':
                self.close()
                raise RuntimeError(value if kind=='startup_error' else '模型进程启动响应无效。')
            self.ready=True
        self.connection.send((method,args))
        while True:
            kind,value=self._receive(task)
            if kind=='progress':task.signals.progress.emit(*value)
            elif kind=='preview':
                if getattr(task.signals,'preview',None):task.signals.preview.emit(value)
            elif kind=='result':return value
            elif kind=='error':raise RuntimeError(value)
            else:
                self.close();raise RuntimeError('模型进程响应无效。')

    def preprocess(self,image,config,bounds,task):return self._call('preprocess',(image,config,bounds),task)
    def prepare_model(self,config,task):return self._call('prepare_model',(config,),task)
    def predict(self,image,config,request,task):return self._call('predict',(image,config,request),task)
    def preview(self,image,config,request,task):return self._call('preview',(image,config,request),task)
    def automatic(self,image,config,bounds,grid,task,level='detail',guidance=None):
        raise ValueError('全图分割功能已移除，请使用正负点或框选逐个标注目标。')

    def close(self):
        if self.cancel_event is not None:self.cancel_event.set()
        self.ready=False;self.cancel_event=None
        if self.connection is not None:
            try:self.connection.send(None)
            except (OSError,EOFError):pass
            self.connection.close();self.connection=None
        if self.process is not None:
            self.process.join(timeout=2)
            if self.process.is_alive():self.process.terminate();self.process.join(timeout=2)
            self.process.close();self.process=None
