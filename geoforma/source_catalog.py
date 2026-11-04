"""Shared source paths for portable projects and non-destructive publication."""
import os
import copy
from pathlib import Path


def project_sources(project):
    return [*project.get('images',[]),*project.get('references',[])]


def guard_snapshot(project):
    """Detach only the paths needed to protect every source during publication."""
    result=[]
    for source in project_sources(project):
        record={key:copy.deepcopy(source[key]) for key in ('path','source_paths') if key in source}
        provenance=source.get('import_list')
        if provenance:
            record['import_list']={key:copy.deepcopy(provenance[key]) for key in ('source','source_paths') if key in provenance}
        result.append(record)
    return result


def relocate_sources(project,base,relative=False):
    """Resolve on load, relativize only a detached payload on save."""
    base=Path(base).resolve()
    def relocate(value):
        path=Path(value)
        if not path.is_absolute():path=base/path
        if not relative:return str(path.resolve())
        try:return os.path.relpath(path,base)
        except ValueError:return str(path)
    for source in project_sources(project):
        source['path']=relocate(source['path'])
        if 'source_paths' in source:source['source_paths']=[relocate(p) for p in source['source_paths']]
        provenance=source.get('import_list')
        if isinstance(provenance,dict) and provenance.get('source'):
            provenance['source']=relocate(provenance['source'])
        if isinstance(provenance,dict) and 'source_paths' in provenance:provenance['source_paths']=[relocate(p) for p in provenance['source_paths']]


class SourceGuard:
    """Index once per operation, including reference rasters and VRT dependencies."""
    def __init__(self,sources,open_files=None):
        self.paths=set();inspected=set();open_files=open_files or {}
        for source in sources:
            self.paths.add(Path(source['path']).resolve())
            self.paths.update(Path(p).resolve() for p in source.get('source_paths',[]))
            provenance=source.get('import_list',{})
            if provenance.get('source'):self.paths.add(Path(provenance['source']).resolve())
            self.paths.update(Path(p).resolve() for p in provenance.get('source_paths',[]))
            # VRTs can be edited outside GeoForma; inspect their current sources.
            # Legacy ordinary TIFF records need no raster read for every autosave.
            path=Path(source['path'])
            if path.suffix.lower()=='.vrt' and path.resolve() not in inspected and path.exists():
                resolved=path.resolve()
                if resolved in open_files:files=open_files[resolved]
                else:
                    import rasterio
                    with rasterio.open(path) as dataset:files=dataset.files
                self.paths.update(Path(p).resolve() for p in files)
                inspected.add(resolved)

    def check(self,*outputs):
        if any(Path(path).resolve() in self.paths for path in outputs):
            raise ValueError('输出不能覆盖源影像（主影像、参考影像）、VRT 引用源或导入来源文件，请使用其他路径。')
