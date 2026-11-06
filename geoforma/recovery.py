"""Locate a previous workspace without opening projects or source rasters."""
from pathlib import Path
from functools import lru_cache
from .project_files import PROJECT_SUFFIX,RECOVERY_NAME


@lru_cache(maxsize=16)
def _has_data(path,mtime,size,ctime):
    from .atomic_io import read_json
    project=read_json(path,max_bytes=256*1024**2)
    return isinstance(project,dict) and bool(project.get('images') or project.get('references'))


def discard_saved_untitled(data_root,cache_id):
    """Remove only the current project's temporary recovery after first save."""
    from .atomic_io import read_json
    if not isinstance(cache_id,str) or not cache_id:return False
    root=Path(data_root).resolve();directory=root/'recovery';path=directory/RECOVERY_NAME
    if directory.is_symlink() or directory.is_junction() or path.is_symlink() or path.is_junction():return False
    if not path.is_file() or not path.resolve().is_relative_to(root):return False
    record=read_json(path,max_bytes=256*1024**2)
    if not isinstance(record,dict) or record.get('cache_id')!=cache_id:return False
    path.unlink();return True


def recovery_target(settings,data_root,legacy_root=None):
    def stamp(base,untitled=False):
        # A named project's recovery is meaningful only while its project file
        # still exists; a stray sidecar must not resurrect a moved project.
        if base.suffix.lower()!=PROJECT_SUFFIX:return None
        if not untitled and not base.is_file():return None
        try:
            if not base.is_file():return None
            stat=base.stat()
            if untitled and not _has_data(str(base),stat.st_mtime_ns,stat.st_size,stat.st_ctime_ns):return None
            return stat.st_mtime_ns
        except (OSError,ValueError,TypeError):return None
    roots=[Path(data_root)]
    if legacy_root is not None and Path(legacy_root)!=Path(data_root):roots.append(Path(legacy_root))
    untitled=[root/'recovery'/RECOVERY_NAME for root in roots]
    remembered=settings.value('recovery/last_work','')
    if not remembered:return None
    base=Path(remembered)
    from .cache_recovery import remap_migrated_path
    base=remap_migrated_path(base,'recoveries',preserve_existing=False) or base
    return base if stamp(base,base in untitled) is not None else None
