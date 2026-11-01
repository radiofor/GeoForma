"""Locate a previous workspace without opening projects or source rasters."""
from pathlib import Path


def recovery_target(settings,data_root,legacy_root=None):
    def stamp(base):
        paths=[base,Path(str(base)+'.autosave')]
        times=[]
        for path in paths:
            try:
                if path.is_file():times.append(path.stat().st_mtime_ns)
            except OSError:pass
        return max(times) if times else None
    roots=[Path(data_root)]
    if legacy_root is not None and Path(legacy_root)!=Path(data_root):roots.append(Path(legacy_root))
    untitled=[root/'recovery'/'untitled.geoforma.json' for root in roots]
    remembered=settings.value('recovery/last_work','')
    if remembered:
        base=Path(remembered)
        from .cache_recovery import remap_migrated_path
        base=remap_migrated_path(base,'recoveries',preserve_existing=False) or base
        if base not in untitled and stamp(base) is not None:return base
    # Compatibility with work saved before the explicit recovery button.
    bases=untitled
    last=settings.value('last_project','')
    if last:bases.append(Path(last))
    available=[(stamp(base),base) for base in bases]
    available=[entry for entry in available if entry[0] is not None]
    return max(available,key=lambda entry:entry[0])[1] if available else None
