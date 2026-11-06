"""Latest-view display scheduler with bounded decoded-window reuse."""
import copy
from collections import OrderedDict
from dataclasses import dataclass
from PySide6.QtCore import QObject,Signal
from ..domain import digest
from ..tasks import Task


def display_snapshot(image):
    # Drafts and saved annotations are not inputs to the raster reader.
    return copy.deepcopy({k:v for k,v in image.items() if k in ('id','path','width','height','fingerprint','display_recipe','transform','crs','assigned_crs','_reference')})


def display_key(image,window,size):
    return digest({'source':image.get('fingerprint',image['path']),'recipe':image['display_recipe'],'window':window,'size':size})


@dataclass(frozen=True)
class RasterRequest:
    key:str
    generation:int
    revision:int
    window:tuple
    size:int
    overview:bool
    image:dict


class RasterRenderQueue(QObject):
    rendered=Signal(object,object,bool)
    error=Signal(str)
    activity=Signal(object)
    idle=Signal()

    def __init__(self,pool,reader,parent=None,max_bytes=96*1024**2):
        super().__init__(parent);self.pool=pool;self.reader=reader;self.max_bytes=max_bytes
        self.task=None;self.active_request=None;self.pending_overview=None;self.pending_detail=None;self.cache=OrderedDict();self.cache_bytes=0
        self.generation=0;self.revision=0;self.cache_epoch=0;self.closed=False;self.displayed={};self.wanted={};self.reads=0;self.hits=0;self.discarded=0

    def viewport_changed(self):self.revision+=1

    def request(self,image,generation,window,size,overview=False):
        if self.closed:return
        self.generation=generation
        # Working drafts can be very large; they are not display inputs.
        snapshot=display_snapshot(image)
        key=display_key(snapshot,window,size)
        request=RasterRequest(key,generation,self.revision,tuple(window),size,overview,snapshot)
        self.wanted[overview]=(generation,key)
        slot='pending_overview' if overview else 'pending_detail'
        if self.displayed.get(overview)==(generation,key):
            setattr(self,slot,None);self.hits+=1;return
        if key in self.cache:
            setattr(self,slot,None);self._start(request);return
        active=self.active_request
        if self.task is not None and active is not None and (active.key,active.generation,active.revision,active.overview)==(key,generation,request.revision,overview):
            setattr(self,slot,None);return
        if self.task is not None:setattr(self,slot,request);return
        self._start(request)

    def _valid(self,request):
        return (not self.closed and request.generation==self.generation and
                self.wanted.get(request.overview)==(request.generation,request.key) and
                (request.overview or request.revision==self.revision))

    def _publish(self,request,value):
        if not self._valid(request):self.discarded+=1;return
        self.displayed[request.overview]=(request.generation,request.key)
        self.rendered.emit(value,request.window,request.overview)

    def _start(self,request):
        if request.key in self.cache:
            self.hits+=1;self.cache.move_to_end(request.key);self._publish(request,self.cache[request.key]);return
        self.reads+=1
        task=Task(lambda t:self.reader(request.image,request.window,request.image['display_recipe'],request.size));self.task=task;self.active_request=request;self.activity.emit(task)
        epoch=self.cache_epoch
        def result(value):
            if self.closed:return
            if epoch!=self.cache_epoch:self.discarded+=1;return
            size=sum(v.nbytes for v in value)
            if size<=self.max_bytes:
                for array in value:array.setflags(write=False)
                if request.key in self.cache:self.cache_bytes-=sum(v.nbytes for v in self.cache.pop(request.key))
                self.cache[request.key]=value;self.cache_bytes+=size
                while self.cache_bytes>self.max_bytes:
                    _,removed=self.cache.popitem(last=False);self.cache_bytes-=sum(v.nbytes for v in removed)
            self._publish(request,value)
        def finished():
            self.task=None;self.active_request=None;self.activity.emit(None)
            self._drain_pending()
            if self.task is None:self.idle.emit()
        task.signals.result.connect(result);task.signals.error.connect(lambda message:self.error.emit(message) if self._valid(request) else None);task.signals.finished.connect(finished);self.pool.start(task)

    def _drain_pending(self):
        # Keep the full-image overview as well as the latest visible detail.
        # Cached requests complete synchronously, so keep draining until a
        # background read starts or both slots are empty.
        while not self.closed and self.task is None:
            if self.pending_overview is not None:
                request=self.pending_overview;self.pending_overview=None
            elif self.pending_detail is not None:
                request=self.pending_detail;self.pending_detail=None
            else:return
            if self._valid(request):self._start(request)
            else:self.discarded+=1

    def reset(self,generation,clear_cache=False):
        self.generation=generation;self.viewport_changed();self.pending_overview=None;self.pending_detail=None;self.displayed.clear();self.wanted.clear()
        if clear_cache:
            self.cache_epoch+=1;self.cache.clear();self.cache_bytes=0

    def prime(self,image,window,size,value):
        key=display_key(image,window,size)
        amount=sum(v.nbytes for v in value)
        if amount>self.max_bytes:return
        for array in value:array.setflags(write=False)
        if key in self.cache:self.cache_bytes-=sum(v.nbytes for v in self.cache.pop(key))
        self.cache[key]=value;self.cache_bytes+=amount
        while self.cache_bytes>self.max_bytes:
            _,removed=self.cache.popitem(last=False);self.cache_bytes-=sum(v.nbytes for v in removed)

    def has_cached(self,image,window,size):return display_key(image,window,size) in self.cache

    def close(self):self.closed=True;self.pending_overview=None;self.pending_detail=None;self.cache.clear();self.cache_bytes=0
