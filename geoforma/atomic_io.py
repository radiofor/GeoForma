"""Atomic local publication shared by projects, caches and runtime metadata."""
from contextlib import contextmanager
import json
from math import isfinite
import os
from pathlib import Path
import tempfile
import threading
import time
import weakref


_locks_guard=threading.Lock()
_target_locks=weakref.WeakValueDictionary()


def _target_lock(target):
    key=os.path.normcase(os.path.abspath(target))
    with _locks_guard:
        lock=_target_locks.get(key)
        if lock is None:
            lock=threading.Lock();_target_locks[key]=lock
        return lock


def replace_file(source,target):
    # Concurrent rename/open operations and virus scanners can briefly lock a
    # Windows destination. Retry only sharing/access errors, with a strict bound.
    # Separate writers in this process should not contend for the same target;
    # unrelated paths remain independent. External locks still use bounded retry.
    with _target_lock(target):
        for attempt in range(8):
            try:os.replace(source,target);return
            except PermissionError as error:
                if os.name!='nt' or getattr(error,'winerror',None) not in (5,32,33) or attempt==7:raise
                time.sleep(min(.01*2**attempt,.1))


@contextmanager
def atomic_target(path,suffix='.tmp'):
    """Each writer owns a unique sibling file; failed writes leave the target intact."""
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    descriptor,name=tempfile.mkstemp(prefix='.'+path.name+'.',suffix=suffix,dir=path.parent)
    os.close(descriptor);temporary=Path(name)
    try:
        yield temporary
        # Windows _commit requires a writable handle even after the writer closed.
        with temporary.open('r+b') as stream:os.fsync(stream.fileno())
        replace_file(temporary,path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_json(path,value,indent=None):
    with atomic_target(path) as temporary:
        with temporary.open('w',encoding='utf-8') as stream:
            json.dump(value,stream,ensure_ascii=False,indent=indent,allow_nan=False)


def _invalid_constant(value):raise ValueError('JSON contains a non-finite number: '+value)


def _finite_float(value):
    number=float(value)
    if not isfinite(number):_invalid_constant(value)
    return number


def _unique_object(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('JSON contains a duplicate key: '+key)
        result[key]=value
    return result


def read_json(path,max_bytes=16*1024**2):
    if type(max_bytes) is not int or max_bytes<=0:raise ValueError('JSON size limit must be positive.')
    with Path(path).open('rb') as stream:
        size=os.fstat(stream.fileno()).st_size
        if size>max_bytes:raise ValueError('JSON 文件超过允许大小，未加载。')
        payload=stream.read(min(size+1,max_bytes+1))
        if stream.read(1):raise ValueError('JSON 文件在读取时发生变化，请重试。')
    if len(payload)>max_bytes:raise ValueError('JSON 文件超过允许大小，未加载。')
    return json.loads(payload.decode('utf-8-sig'),parse_constant=_invalid_constant,
                      parse_float=_finite_float,object_pairs_hook=_unique_object)
