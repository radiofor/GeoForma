"""Resolve missing project rasters without touching the saved project."""
from pathlib import Path
from .reference_catalog import reference_stem


def missing_sources(project):
    result=[]
    for kind in ('images','references'):
        for source in project.get(kind,[]):
            path=Path(source['path'])
            missing=not path.is_file()
            if not missing and path.suffix.lower()=='.vrt':
                try:
                    import rasterio
                    with rasterio.open(path) as dataset:
                        missing=any(not Path(p).is_file() for p in dataset.files)
                except (OSError,ValueError):missing=True
            if missing:result.append((kind,source))
    return result


def relink_source(source,path,project=None,kind=None):
    from .raster import inspect_source
    replacement=inspect_source(path)
    # Reference matching is keyed by group and filename stem. A new stem would
    # silently detach it from its main image even when raster grids match.
    if kind=='references' and reference_stem(replacement['path'])!=reference_stem(source['path']):
        raise ValueError('参考影像的新文件名需要与原文件名一致，才能继续匹配主影像。')
    if kind=='images' and project is not None:
        old_stem=reference_stem(source['path'])
        if reference_stem(replacement['path'])!=old_stem and any(reference_stem(ref['path'])==old_stem for ref in project.get('references',[])):
            raise ValueError('该影像有关联的参考影像，新文件名需要与原文件名一致，才能保持参考匹配。')
    if project is not None:
        target=Path(replacement['path'])
        for other in project.get(kind,[]):
            if other is source:continue
            if Path(other['path']).resolve()==target:
                raise ValueError('所选数据已存在于项目中。')
            if kind=='references' and other['group'].casefold()==source['group'].casefold() and reference_stem(other['path'])==reference_stem(target):
                raise ValueError('同一类型已存在同名参考影像。')
    for key in ('width','height','bands','crs'):
        if replacement[key]!=source[key]:raise ValueError('影像的尺寸、波段、数据类型或坐标系与原数据不一致。')
    expected=source['dtypes']
    if len(expected)==1:expected=expected*source['bands']
    if replacement['dtypes']!=expected:raise ValueError('影像的尺寸、波段、数据类型或坐标系与原数据不一致。')
    if any(abs(a-b)>1e-9*max(1,abs(a),abs(b)) for a,b in zip(replacement['transform'],source['transform'])):
        raise ValueError('影像的地理变换与原数据不一致。')
    for key in ('path','fingerprint','source_paths','source_files'):
        source[key]=replacement[key]
    # The source path contributes to the cache fingerprint; old model results
    # and any in-progress inference are no longer valid.
    source['ready']=False
    for key in ('prepared_full_signature','prepared_cache_revision','preparation_state','import_list'):
        source.pop(key,None)
    if kind=='images':source['_relinked']=True


def validate_resolved_project(project):
    """Validate the entire edited project before staging or committing it."""
    from .project_validation import validate_project
    from .history import validate_history
    validate_project(project);validate_history(project)


def remove_source(project,kind,source):
    project[kind].remove(source)
    if kind!='images':return
    image_id=source['id']
    project['labels']=[label for label in project['labels'] if label['image_id']!=image_id]
    # Compound undo operations can span images; retaining only portions could
    # replay an invalid operation. Explain this before removal in the dialog.
    project.pop('history',None)
    workspace=project.get('workspace',{})
    if workspace.get('image_id')==image_id:
        for key in ('image_id','draft','reshape','navigation','view_window'):
            workspace.pop(key,None)
