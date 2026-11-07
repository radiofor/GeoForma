"""Latest-request-only background geometry work with bounded reversible caching."""
from collections import OrderedDict
from PySide6.QtCore import QObject,Signal,QTimer,QThreadPool
from ..tasks import Task
from .scene_layers import geometry_path
from ..smoothing_cache import SmoothingGeometryCache


def prepare_paths(records,value,task=None):
    sources={l['id']:l['geometry'] for l in records}
    for label in value:
        if task:task.check()
        label['_render_path']=geometry_path(label['geometry'])
        if '_bounds' not in label:
            bounds=label['_render_path'].boundingRect()
            label['_bounds']=[bounds.left(),bounds.top(),bounds.right(),bounds.bottom()]
        label['_source_geometry']=sources[label['id']];label['_source_path']=geometry_path(sources[label['id']])
    return value


class SmoothingQueue(QObject):
    updated=Signal()
    error=Signal(str)
    idle=Signal()
    activity=Signal(object)

    def __init__(self,parent=None):
        super().__init__(parent);self.pool=QThreadPool(self);self.pool.setMaxThreadCount(1)
        self.task=None;self.pending=None;self.key=None;self.cache=OrderedDict();self.last=None;self.closed=False
        self.context=None;self.pinned=None;self._stale_last=None
        self.geometry_cache=SmoothingGeometryCache()
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(35);self.timer.timeout.connect(self._start)

    def set_context(self,context):
        if self.context!=context:
            self.context=context;self.clear_pinned()

    def clear_pinned(self):
        self.pinned=None
        # A result signal may still be notifying other listeners. Defer cleanup
        # until the worker finishes, and never discard a newer replacement.
        if self.task is not None:self._stale_last=self.last
        else:self._drop_uncached_last()

    def validate_pinned(self,records):
        if self.pinned is None:return
        previous=self.pinned[1]
        if len(previous)!=len(records) or any(
            a['id']!=b['id'] or a['geometry'] is not b['geometry'] or a.get('status')!=b.get('status')
            for a,b in zip(previous,records)):
            self.clear_pinned()

    def request(self,key,records,fn,*,immediate=False,retain=False):
        if self.closed:return None
        if self.last and self.last[0]==key:
            if self.key!=key:
                self.key=key;self.pending=None;self.timer.stop()
                if self.task:self.task.cancel()
            if retain:self.pinned=self.last
            return self.last[2]
        if self.pinned and self.pinned[0]==key:
            self.key=key;self.pending=None;self.timer.stop()
            if self.task:self.task.cancel()
            self.last=self.pinned;return self.last[2]
        if key in self.cache:
            self.key=key;self.pending=None;self.timer.stop()
            if self.task:self.task.cancel()
            self.cache.move_to_end(key);self.last=(key,records,self.cache[key][1])
            if retain:self.pinned=self.last
            return self.last[2]
        if key!=self.key:
            self.key=key;self.pending=(key,records,fn,retain,self.context)
            if self.task:self.task.cancel()
            self.timer.start(0 if immediate else 35)
        return None

    def _start(self):
        if self.closed or self.task or not self.pending:return
        key,records,fn,retain,context=self.pending;self.pending=None
        def work(task):
            return prepare_paths(records,fn(task),task)
        task=Task(work);self.task=task;self.activity.emit(task)
        def done(value):
            if self.closed or task.cancel_event.is_set():return
            weight=0
            for label in value:
                geometry=label['geometry'];polygons=geometry['coordinates'] if geometry['type']=='MultiPolygon' else [geometry['coordinates']]
                weight+=sum(len(ring) for polygon in polygons for ring in polygon)*128
                source=label['_source_geometry'];polygons=source['coordinates'] if source['type']=='MultiPolygon' else [source['coordinates']]
                weight+=sum(len(ring) for polygon in polygons for ring in polygon)*32
            # Oversized current results use the dedicated slot; they should not
            # evict every otherwise reusable entry from the bounded LRU.
            if weight<=16*1024**2:
                self.cache[key]=(records,value,weight)
                while len(self.cache)>8 or sum(v[2] for v in self.cache.values())>16*1024**2:
                    self.cache.popitem(last=False)
            if key==self.key:
                self.last=(key,records,value)
                if retain and context==self.context:self.pinned=self.last
                self.updated.emit()
        def failed(message):
            if not self.closed and not task.cancel_event.is_set() and key==self.key:self.error.emit(message)
        def finished():
            self.task=None;self.activity.emit(None)
            if self._stale_last is not None and self.last is self._stale_last:self._drop_uncached_last()
            self._stale_last=None
            if self.key is None:self._drop_uncached_last()
            if self.closed:self.idle.emit();return
            if self.pending and not self.timer.isActive():self._start()
            if self.task is None:self.idle.emit()
        task.signals.result.connect(done);task.signals.error.connect(failed);task.signals.finished.connect(finished);self.pool.start(task)

    def stop(self):
        self.key=None;self.pending=None;self.timer.stop()
        if self.task:self.task.cancel()
        else:self._drop_uncached_last()

    def _drop_uncached_last(self):
        # Keep only bounded entries and the current image's pinned result.
        if self.last:
            cached=self.cache.get(self.last[0])
            if (cached is None or cached[1] is not self.last[2]) and (self.pinned is None or self.pinned[2] is not self.last[2]):self.last=None

    def prime(self,key,records,value,*,retain=False,context=None):
        self.stop();self.set_context(context);self.key=key;self.last=(key,records,value)
        if retain:self.pinned=self.last

    def clear(self):
        self.stop();self.cache.clear();self.geometry_cache.clear();self.last=None;self.pinned=None;self.context=None;self._stale_last=None

    def close(self):
        self.closed=True;self.clear()
