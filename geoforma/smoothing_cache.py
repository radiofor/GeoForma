"""Thread-safe, bounded cache of independent per-geometry smoothing work."""
from collections import OrderedDict
from threading import Lock
from .label_index import vertex_count


def _shape_vertices(geometry):
    parts=geometry.geoms if geometry.geom_type=='MultiPolygon' else (geometry,)
    return sum(len(part.exterior.coords)+sum(len(ring.coords) for ring in part.interiors) for part in parts)


class SmoothingGeometryCache:
    def __init__(self,max_entries=2048,max_bytes=24*1024**2):
        self.max_entries=max_entries;self.max_bytes=max_bytes;self.entries=OrderedDict();self.bytes=0;self.epoch=0;self.lock=Lock()

    def snapshot(self):
        with self.lock:return self.epoch

    def get(self,source,value,epoch):
        key=(id(source),value)
        with self.lock:
            if epoch!=self.epoch:return None
            entry=self.entries.get(key)
            if entry is None or entry[0] is not source:return None
            self.entries.move_to_end(key);return entry[1],entry[2]

    def put(self,source,value,raw,smoothed,epoch):
        weight=512+128*(vertex_count(source)+_shape_vertices(smoothed));key=(id(source),value)
        with self.lock:
            if epoch!=self.epoch:return
            previous=self.entries.pop(key,None)
            if previous:self.bytes-=previous[3]
            if weight>self.max_bytes:return
            self.entries[key]=(source,raw,smoothed,weight);self.bytes+=weight
            while len(self.entries)>self.max_entries or self.bytes>self.max_bytes:
                _,entry=self.entries.popitem(last=False);self.bytes-=entry[3]

    def clear(self):
        with self.lock:self.epoch+=1;self.entries.clear();self.bytes=0
