"""Bounded reads of app-owned, uncompressed Torch feature archives."""
from pathlib import Path,PurePosixPath
from zipfile import ZipFile,ZIP_STORED,BadZipFile
import re


def feature_directory(root):
    """Keep cache reads and writes inside the managed, non-linked directory."""
    from .project_cache import checked_directory
    return checked_directory(root,'cache/features')


def feature_path(root,key):
    if not isinstance(key,str) or not re.fullmatch('[a-f0-9]{64}',key):raise ValueError('特征缓存标识无效。')
    path=feature_directory(root)/(key+'.pt')
    if path.is_symlink() or path.is_junction():raise ValueError('特征缓存文件不能为链接。')
    return path


def load_features(path,expected_bytes):
    path=Path(path);limit=expected_bytes*2+8*1024**2
    try:
        if path.is_symlink() or path.is_junction() or not path.is_file() or path.stat().st_size>limit:return None
        with ZipFile(path) as archive:
            members=archive.infolist()
            if len(members)>4096 or sum(item.file_size for item in members)>limit:return None
            if any(item.compress_type!=ZIP_STORED or item.flag_bits&1 or '..' in PurePosixPath(item.filename).parts for item in members):return None
        import torch
        # Do not retain file mappings: cache cleanup must work while CPU models
        # retain their current feature tensors, including on Windows.
        return torch.load(path,map_location='cpu',weights_only=True)
    except (OSError,ValueError,RuntimeError,KeyError,TypeError,BadZipFile,EOFError):return None
