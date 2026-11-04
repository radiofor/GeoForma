"""Reconcile saved preparation signatures against existing feature archives."""
import hashlib
import os
from pathlib import Path, PurePosixPath
from zipfile import ZipFile, ZIP_STORED, BadZipFile
from .domain import digest, tiles
from .workflow import full_bounds, preparation_signature
from .model_catalog import adapter_schema, sam2_descriptor, SAM3_COMMIT


def remap_migrated_path(original, kind, *, preserve_existing=True):
    """Find a recorded migrated model or recovery path without guessing."""
    from .atomic_io import read_json
    from .domain import data_dir
    if not isinstance(original,(str,Path)) or not str(original):return None
    try:
        path=Path(original)
        if not path.is_absolute() or (preserve_existing and path.is_file()):return None
        history=read_json(data_dir()/'resource-migration-history.json')
        if not isinstance(history,dict) or history.get('kind')!='geoforma-resource-migration-history-v1':return None
        entries=history.get('migrations')
        if not isinstance(entries,list):return None
        folder={'models':'models','recoveries':'recovery'}.get(kind)
        if not folder:return None
        norm=lambda p:os.path.normcase(os.path.abspath(p))
        for entry in entries:
            if not isinstance(entry,dict):continue
            source=entry.get('source');destination=entry.get('destination');files=entry.get(kind)
            if not isinstance(source,str) or not isinstance(destination,str) or not isinstance(files,list):continue
            src=Path(source);dst=Path(destination)
            if not src.is_absolute() or not dst.is_absolute():continue
            for item in files:
                if not isinstance(item,str) or '\\' in item:continue
                relative=PurePosixPath(item)
                if len(relative.parts)!=2 or relative.parts[0]!=folder or any(p in ('.','..') for p in relative.parts) or relative.is_absolute():continue
                if norm(path)==norm(src.joinpath(*relative.parts)):
                    path=dst.joinpath(*relative.parts);break
        if norm(path)==norm(original) or path.is_symlink() or path.is_junction() or path.parent.is_symlink() or path.parent.is_junction():return None
        return path if path.is_file() else None
    except (OSError,ValueError,TypeError,AttributeError):return None


def remap_migrated_checkpoint(project):
    """Restore a missing managed weight path after a verified migration."""
    model=project.get('model',{})
    path=remap_migrated_path(model.get('checkpoint'),'models')
    if path is None:return False
    model['checkpoint']=str(path)
    return True


def descriptor(model, image, window, weight_hash):
    family=model.get('backend','sam')
    config=dict(model,weights_sha256=weight_hash)
    if family in ('sam2','sam2.1'):return sam2_descriptor(config,image,window)
    common={'schema':adapter_schema(family),'source':image['fingerprint'],
            'grid':[image['width'],image['height'],image['transform']],
            'recipe':image['model_recipe'],'window':list(window),'weights':weight_hash,
            'variant':model['variant']}
    if family=='sam':return common
    if family=='sam3':return dict(common,backend=family,code=SAM3_COMMIT,
                                  resize='sam3_square_1008',precision='bf16_autocast_fp32_cache',postprocessing=False)
    raise ValueError('Unknown model family')


def valid_archive(path,limit):
    try:
        if path.is_symlink() or path.is_junction() or not path.is_file() or path.stat().st_size>limit:return False
        with ZipFile(path) as archive:
            entries=archive.infolist()
            return bool(entries and len(entries)<=4096 and sum(e.file_size for e in entries)<=limit
                        and all(e.compress_type==ZIP_STORED and not e.flag_bits&1 and '..' not in PurePosixPath(e.filename).parts for e in entries)
                        and archive.testzip() is None)
    except (OSError,ValueError,BadZipFile,RuntimeError):return False


def reconcile_prepared(project,root,revision,task=None):
    """Only recover mismatched signatures when every expected cache block exists intact.

    The backend still validates payload metadata and tensor shapes when reading a block.
    """
    def check():
        if task:task.check()
    model=project['model'];candidates=[image for image in project['images']
        if image.get('ready') and image.get('prepared_cache_revision')==revision and revision
        and image.get('prepared_full_signature')!=preparation_signature(image,model)]
    if not candidates:return 0
    from .feature_cache import feature_directory
    try:folder=feature_directory(root)
    except (OSError,ValueError):return 0
    try:
        check();sha=hashlib.sha256()
        with Path(model['checkpoint']).open('rb') as stream:
            while block:=stream.read(4*1024*1024):check();sha.update(block)
        weight_hash=sha.hexdigest()
    except OSError:return 0
    from .raster import fingerprint
    family=model.get('backend','sam')
    limit={'sam':4,'sam2':20,'sam2.1':20,'sam3':26}.get(family,0)*2*1024**2+8*1024**2
    recovered=0
    for image in candidates:
        check()
        try:
            if fingerprint(image['path'])!=image['fingerprint']:continue
            windows=tiles(full_bounds(image),image['width'],image['height'])
            for window in windows:
                check();key=digest(descriptor(model,image,window,weight_hash))
                if not valid_archive(folder/(key+'.pt'),limit):break
            else:
                image['prepared_full_signature']=preparation_signature(image,model);recovered+=1
        except (OSError,ValueError,KeyError):continue
    return recovered
