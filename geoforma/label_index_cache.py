"""Bounded per-image label indexes; callers validate record signatures."""
from collections import OrderedDict


class LabelIndexCache:
    def __init__(self,max_entries=4,max_bytes=32*1024**2):
        self.max_entries=max_entries;self.max_bytes=max_bytes;self.entries=OrderedDict();self.bytes=0

    def get(self,context,signature):
        entry=self.entries.get(context)
        if entry is None:return None
        if entry[0]!=signature:
            self.bytes-=self.entries.pop(context)[2];return None
        self.entries.move_to_end(context);return entry[1]

    def put(self,context,signature,index):
        previous=self.entries.pop(context,None)
        if previous:self.bytes-=previous[2]
        weight=index.cache_weight
        if weight>self.max_bytes:return
        self.entries[context]=(signature,index,weight);self.bytes+=weight
        while len(self.entries)>self.max_entries or self.bytes>self.max_bytes:
            _,entry=self.entries.popitem(last=False);self.bytes-=entry[2]

    def clear(self):self.entries.clear();self.bytes=0
    def __bool__(self):return bool(self.entries)
