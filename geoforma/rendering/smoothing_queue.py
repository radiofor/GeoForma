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
        self.geometry_cache=SmoothingGeometryCache()
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(35);self.timer.timeout.connect(self._start)

    def request(self,key,records,fn):
        if self.closed:return None
        if self.last and self.last[0]==key:
            if self.key!=key:
                self.key=key;self.pending=None;self.timer.stop()
                if self.task:self.task.cancel()
            return self.last[2]
        if key in self.cache:
            self.key=key;self.pending=None;self.timer.stop()
            if self.task:self.task.cancel()
            self.cache.move_to_end(key);self.last=(key,records,self.cache[key][1]);return self.last[2]
        if key!=self.key:
            self.key=key;self.pending=(key,records,fn)
            if self.task:self.task.cancel()
            self.timer.start()
        return None

    def _start(self):
        if self.closed or self.task or not self.pending:return
        key,records,fn=self.pending;self.pending=None
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
            self.cache[key]=(records,value,weight)
            # Bound both the number and approximate coordinate memory of cached results.
            while len(self.cache)>8 or sum(v[2] for v in self.cache.values())>16*1024**2:
                self.cache.popitem(last=False)
                if not self.cache:break
            if key==self.key:self.last=(key,records,value);self.updated.emit()
        def failed(message):
            if not self.closed and not task.cancel_event.is_set() and key==self.key:self.error.emit(message)
        def finished():
            self.task=None;self.activity.emit(None)
            if self.closed:self.idle.emit();return
            if self.pending and not self.timer.isActive():self._start()
            if self.task is None:self.idle.emit()
        task.signals.result.connect(done);task.signals.error.connect(failed);task.signals.finished.connect(finished);self.pool.start(task)

    def stop(self):
        self.key=None;self.pending=None;self.timer.stop()
        if self.task:self.task.cancel()

    def prime(self,key,records,value):
        self.stop();self.key=key;self.last=(key,records,value)

    def clear(self):
        self.stop();self.cache.clear();self.geometry_cache.clear();self.last=None

    def close(self):
        self.closed=True;self.clear()
