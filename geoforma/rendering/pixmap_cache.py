"""Bounded GUI-thread reuse of pixmaps built from immutable raster arrays."""
from collections import OrderedDict


class RasterPixmapCache:
    def __init__(self,max_entries=8,max_bytes=48*1024**2):
        self.max_entries=max_entries;self.max_bytes=max_bytes;self.entries=OrderedDict();self.bytes=0

    def get(self,array,valid):
        if array.flags.writeable or valid.flags.writeable:return None
        key=(id(array),id(valid));entry=self.entries.get(key)
        if entry is None or entry[0] is not array or entry[1] is not valid:return None
        self.entries.move_to_end(key);return entry[2]

    def put(self,array,valid,pixmap):
        if array.flags.writeable or valid.flags.writeable:return
        key=(id(array),id(valid));previous=self.entries.pop(key,None)
        if previous:self.bytes-=previous[3]
        weight=array.nbytes+valid.nbytes+pixmap.width()*pixmap.height()*4
        if weight>self.max_bytes:return
        self.entries[key]=(array,valid,pixmap,weight);self.bytes+=weight
        while len(self.entries)>self.max_entries or self.bytes>self.max_bytes:
            _,entry=self.entries.popitem(last=False);self.bytes-=entry[3]

    def clear(self):self.entries.clear();self.bytes=0
    def __len__(self):return len(self.entries)
