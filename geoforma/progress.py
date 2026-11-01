"""Shared progress lifecycle; each independent operation owns its own model."""
from dataclasses import dataclass,replace
from PySide6.QtCore import QObject,Signal


@dataclass(frozen=True)
class ProgressState:
    title:str=''
    kind:str|None=None
    stage:str=''
    phase:str='idle'
    current:int=0
    total:int=0
    cancellable:bool=False
    cancelling:bool=False

    @property
    def fraction(self):
        if self.phase=='complete':return 1.
        return self.current/self.total if self.total else None

    @property
    def can_cancel(self):return self.phase=='running' and self.cancellable and not self.cancelling


class ProgressModel(QObject):
    changed=Signal(object)

    def __init__(self,parent=None):
        super().__init__(parent);self.state=ProgressState();self.generation=0

    def _publish(self,state):
        if state!=self.state:self.state=state;self.changed.emit(state)

    def begin(self,title,kind=None,stage='',cancellable=False):
        self.generation+=1
        self._publish(ProgressState(str(title),kind,str(stage),'running',cancellable=bool(cancellable)))
        return self.generation

    def _accepts(self,token):return self.state.phase=='running' and (token is None or token==self.generation)

    def report(self,current=0,total=0,stage='',*,token=None):
        if not self._accepts(token) or self.state.cancelling:return False
        total=max(0,int(total));current=max(0,int(current))
        if total:current=min(current,total)
        self._publish(replace(self.state,current=current,total=total,stage=str(stage)))
        return True

    def request_cancel(self,stage='正在停止…',*,token=None):
        if not self._accepts(token) or not self.state.can_cancel:return False
        self._publish(replace(self.state,cancelling=True,stage=str(stage)));return True

    def finish(self,outcome='complete',stage=None,*,token=None):
        if outcome not in ('complete','cancelled','failed'):raise ValueError('未知进度结果：'+str(outcome))
        if not self._accepts(token):return False
        if self.state.cancelling and outcome=='complete':outcome='cancelled'
        self._publish(replace(self.state,phase=outcome,
                              current=self.state.total if outcome=='complete' and self.state.total else self.state.current,
                              stage=self.state.stage if stage is None else str(stage),cancelling=False))
        return True
