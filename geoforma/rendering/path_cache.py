"""Bounded reuse of immutable source geometry and its Qt painter path."""
from collections import OrderedDict
from ..label_index import vertex_count


class GeometryPathCache:
    def __init__(self,max_entries=4096,max_bytes=16*1024**2):
        self.max_entries=max_entries;self.max_bytes=max_bytes;self.entries=OrderedDict();self.bytes=0

    def get(self,geometry):
        key=id(geometry);entry=self.entries.get(key)
        if entry is None or entry[0] is not geometry:return None
        self.entries.move_to_end(key);return entry[1]

    def put(self,geometry,path):
        key=id(geometry);old=self.entries.pop(key,None)
        if old:self.bytes-=old[2]
        weight=512+128*vertex_count(geometry)
        if weight>self.max_bytes:return
        self.entries[key]=(geometry,path,weight);self.bytes+=weight
        while len(self.entries)>self.max_entries or self.bytes>self.max_bytes:
            _,entry=self.entries.popitem(last=False);self.bytes-=entry[2]

    def clear(self):self.entries.clear();self.bytes=0
    def __contains__(self,key):return key in self.entries
    def __len__(self):return len(self.entries)
