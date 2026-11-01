"""Display-only raster references, aligned to the calculation raster's pixel grid."""
from pathlib import Path
from functools import lru_cache
import copy
import numpy as np
import rasterio
from rasterio.vrt import WarpedVRT
from rasterio.windows import Window
from rasterio.enums import Resampling
from affine import Affine
from .domain import digest
from .nodata import declared_missing_value

MAIN_IMAGE_LABEL='主影像'
REFERENCE_NAME_LIMIT=8


def reference_group_name(value,*,truncate=False):
    if not isinstance(value,str) or not value.strip():raise ValueError('请输入参考类型名称。')
    value=value.strip()
    if any(ord(char)<32 for char in value):raise ValueError('参考类型名称不能包含换行或控制字符。')
    if truncate:value=value[:REFERENCE_NAME_LIMIT].rstrip()
    if len(value)>REFERENCE_NAME_LIMIT:raise ValueError(f'参考类型名称最多 {REFERENCE_NAME_LIMIT} 个字符。')
    if value==MAIN_IMAGE_LABEL:raise ValueError('“主影像”用于原始数据，请使用其他参考类型名称。')
    return value


def reference_origin(path,metadata=None):
    """Display provenance only: retain the original source name after renaming."""
    path=Path((metadata or {}).get('source') or path)
    if path.suffix.lower() in ('.yaml','.yml'):return {'kind':'list','name':path.name}  # Existing project provenance.
    if path.suffix.lower()=='.vrt':return {'kind':'vrt','name':path.name}
    return {'kind':'folder','name':path.parent.name or path.stem}


def suggested_reference_name(paths):
    paths=[Path(path) for path in paths]
    if not paths:return ''
    path=next((p for p in paths if p.suffix.lower()=='.vrt'),None)
    return path.stem if path is not None else paths[0].parent.name or paths[0].stem


def reference_tooltip(reference):
    origin=reference.get('reference_origin') or reference_origin(reference['path'],reference.get('import_list'))
    return f"{reference['group']}\n来源：{origin['name']}\n{reference['path']}"


def matching_references(project,image):
    if not image or not image.get('path') or not project.get('references'):return []
    stem=Path(image['path']).stem.casefold()
    return [ref for ref in project.get('references',[]) if Path(ref['path']).stem.casefold()==stem]


def validate_references(project):
    from .raster_metadata import validate_metadata
    import math
    refs=project.get('references',[])
    if not isinstance(refs,list):raise ValueError('参考影像记录无效。')
    seen=set()
    for ref in refs:
        if not isinstance(ref,dict) or not isinstance(ref.get('path'),str) or not ref['path'] or '\x00' in ref['path'] or not isinstance(ref.get('group'),str) or not ref['group'].strip():raise ValueError('参考影像路径或类型无效。')
        validate_metadata(ref)
        transform=ref.get('transform')
        if any(type(ref.get(key)) is not int or ref[key]<=0 for key in ('width','height')):raise ValueError('参考影像尺寸无效。')
        if not isinstance(transform,(list,tuple)) or len(transform)!=6 or any(type(v) not in (int,float) or not math.isfinite(v) for v in transform):raise ValueError('参考影像网格无效。')
        if transform[0]*transform[4]-transform[1]*transform[3]==0:raise ValueError('参考影像网格不可逆。')
        if not ref.get('display_recipe'):raise ValueError('参考影像显示配置无效。')
        origin=ref.get('reference_origin')
        if origin is not None and (not isinstance(origin,dict) or origin.get('kind') not in ('list','vrt','folder') or not isinstance(origin.get('name'),str) or not origin['name']):raise ValueError('参考影像来源名称无效。')
        key=(ref['group'].casefold(),Path(ref['path']).stem.casefold())
        if key in seen:raise ValueError('同一类型存在重复参考影像。')
        seen.add(key)


def display_descriptor(image,reference=None):
    if reference is None:return image
    result=dict(image);result['_reference']=reference
    result['fingerprint']=digest([image.get('fingerprint'),image['transform'],image.get('assigned_crs') or image.get('crs'),reference['fingerprint'],reference['display_recipe']])
    return result


@lru_cache(maxsize=128)
def _tagged_recipe(path,size,mtime_ns,bands,missing_value):
    from .raster import make_recipe
    return make_recipe({'path':path},list(bands),minimum_span=1e-6,relative_span=1e-6,missing_value=missing_value)


def _recipe_for_missing(reference,missing_value):
    path=Path(reference['path']);stat=path.stat()
    bands=tuple(reference.get('suggested_bands') or reference['display_recipe']['bands'])
    return copy.deepcopy(_tagged_recipe(str(path),stat.st_size,stat.st_mtime_ns,bands,missing_value))


def reference_recipe(image):
    from .raster import make_recipe
    bands=image.get('suggested_bands') or [1,1,1]
    with rasterio.open(image['path']) as source:missing_value=declared_missing_value(source)
    if missing_value is not None:
        stat=Path(image['path']).stat()
        return copy.deepcopy(_tagged_recipe(image['path'],stat.st_size,stat.st_mtime_ns,tuple(bands),missing_value))
    return make_recipe(image,bands,minimum_span=1e-6,relative_span=1e-6)


def read_display(image,window,recipe=None,max_size=None):
    if '_reference' not in image:
        from .raster import read_rgb
        return read_rgb(image,window,recipe,max_size)
    reference=image['_reference'];recipe=reference['display_recipe']
    from .contracts import display_read_shape,validate_recipe
    (x,y,w,h),out_shape=display_read_shape(window,max_size)
    output=np.zeros((*out_shape,3),dtype='uint8');valid=np.ones(out_shape,dtype=bool)
    from contextlib import ExitStack
    with ExitStack() as stack:
        source=stack.enter_context(rasterio.open(reference['path']))
        missing_value=declared_missing_value(source)
        if missing_value is not None:recipe=_recipe_for_missing(reference,missing_value)
        validate_recipe(recipe,reference['bands'])
        crs=image.get('assigned_crs') or image.get('crs')
        alpha=False
        if source.crs and crs:
            options={'src_nodata':missing_value,'nodata':missing_value} if missing_value is not None else {'add_alpha':True}
            alpha=missing_value is None
            ds=stack.enter_context(WarpedVRT(source,crs=crs,transform=Affine(*image['transform']),width=image['width'],height=image['height'],resampling=Resampling.bilinear,**options))
        elif source.width==image['width'] and source.height==image['height'] and list(source.transform)[:6]==image['transform']:
            ds=stack.enter_context(WarpedVRT(source,src_nodata=missing_value,nodata=missing_value,transform=source.transform,width=source.width,height=source.height,resampling=Resampling.bilinear)) if missing_value is not None else source
        else:raise ValueError('参考影像缺少投影，且像元网格与主影像不同，无法对齐。')
        arrays={}
        for channel,(band,(lo,hi)) in enumerate(zip(recipe['bands'],recipe['ranges'])):
            if band not in arrays:arrays[band]=ds.read(band,window=Window(x,y,w,h),out_shape=out_shape,masked=True,resampling=Resampling.bilinear)
            array=arrays[band];values=array.filled(float('nan')).astype('float32') if array.dtype.kind=='f' else array.astype('float32').filled(float('nan'))
            good=~np.ma.getmaskarray(array)&np.isfinite(values);valid&=good
            output[:,:,channel]=np.nan_to_num(np.clip((values-lo)*255/max(hi-lo,1e-12),0,255)).astype('uint8')
        if alpha:valid&=ds.read(ds.count,window=Window(x,y,w,h),out_shape=out_shape,resampling=Resampling.nearest)>0
        else:valid&=ds.dataset_mask(window=Window(x,y,w,h),out_shape=out_shape,resampling=Resampling.nearest)>0
    return output,valid
