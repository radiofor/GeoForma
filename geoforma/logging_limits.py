"""Bound application diagnostic logs without touching unrelated files."""
from pathlib import Path

MAX_LOG_BYTES=512*1024


def append_error(root,text):
    path=Path(root)/'errors.log'
    if path.is_symlink() or path.is_junction():raise ValueError('日志文件不能是链接。')
    encoded=(str(text)+'\n').encode('utf-8',errors='replace')[-MAX_LOG_BYTES:]
    if path.exists() and path.stat().st_size+len(encoded)>MAX_LOG_BYTES:
        with path.open('wb') as stream:stream.write(encoded)
    else:
        with path.open('ab') as stream:stream.write(encoded)
