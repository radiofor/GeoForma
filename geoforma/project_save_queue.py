"""Coalesced project snapshots, independent of Qt widgets and disk writers."""
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectSaveRequest:
    snapshot:dict
    path:Path
    project_path:Path|None
    epoch:int
    revision:int
    title:str
    order:int

    @property
    def destination(self):return self.project_path or self.path

    @property
    def key(self):return self.epoch,self.destination.resolve()


class ProjectSaveQueue:
    """Keep busy true from submission through completion, including dispatch gaps."""
    def __init__(self):
        self.pending=OrderedDict();self.failed=OrderedDict();self.committed={};self.sequence=0;self.busy=False

    def next_order(self):
        self.sequence+=1;return self.sequence

    def stale(self,request):
        return request.order<=self.committed.get(request.destination.resolve(),0)

    def submit(self,request):
        if self.stale(request):return
        self.busy=True
        self.failed.pop(request.key,None);self.pending[request.key]=request

    def pop(self):
        while self.pending:
            _,request=self.pending.popitem(last=False)
            if not self.stale(request):return request
        self.busy=False
        return None

    def complete(self):self.busy=bool(self.pending)

    def defer(self,request):
        if not self.stale(request) and request.key not in self.pending:self.failed[request.key]=request

    def retry_failed(self):
        requests=list(self.failed.values());self.failed.clear()
        for request in requests:self.submit(request)

    def saved(self,path,order):
        destination=Path(path).resolve()
        self.committed[destination]=max(order,self.committed.get(destination,0))
