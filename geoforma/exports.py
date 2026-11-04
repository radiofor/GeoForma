import json
from pathlib import Path
from .export_settings import DEFAULT_LABEL_FIELD
import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.transform import Affine
from shapely.geometry import mapping,box
from shapely.strtree import STRtree
from .atomic_io import atomic_target


def protect_source(image,path,source=None):
    from .source_catalog import SourceGuard
    files={Path(image['path']).resolve():source.files} if source is not None and Path(image['path']).suffix.lower()=='.vrt' else None
    SourceGuard([image],open_files=files).check(path)


def export_vector(image,labels,path,target_crs,task,classes=None,sources=None,label_field=DEFAULT_LABEL_FIELD,protected_paths=()):
    from .vector_export import write_vector
    from .raster import validate_grid
    validate_grid(image)
    from .source_catalog import SourceGuard
    guard=SourceGuard([image,*(sources or [])])
    protected={Path(value).resolve() for value in protected_paths}
    def protect(image,target):
        guard.check(target)
        if Path(target).resolve() in protected:raise ValueError('导出不能覆盖当前项目文件，请选择其他路径。')
    return write_vector(image,labels,path,target_crs,task,classes,protect,label_field=label_field)


def export_raster(image,labels,path,task,classes=None):
    from .export_validation import validate_export_labels
    from .raster import validate_grid_dataset
    with rasterio.open(image['path']) as source:
        missing_value=validate_grid_dataset(source,image)
        codes,geometries=validate_export_labels(image,labels,classes,task)
        protect_source(image,path,source)
        path=Path(path);transform=Affine(*image['transform'])
        crs=image.get('assigned_crs') or image['crs']
        if not crs:raise ValueError('请先指定影像 CRS。')
        tree=STRtree(geometries)
        with atomic_target(path,suffix='.tif') as temp,rasterio.open(temp,'w',driver='GTiff',
            width=image['width'],height=image['height'],count=1,dtype='uint16',crs=crs,transform=transform,nodata=65535,
            tiled=True,blockxsize=512,blockysize=512,compress='deflate',BIGTIFF='IF_SAFER') as dst:
            from .raster_validity import read_valid_mask
            bands=(image.get('model_recipe') or image.get('display_recipe') or {}).get('bands') or [1]
            total=((image['width']+511)//512)*((image['height']+511)//512)
            for i,(_,window) in enumerate(dst.block_windows(1)):
                task.check();bounds=box(window.col_off,window.row_off,window.col_off+window.width,window.row_off+window.height);indices=sorted(int(j) for j in tree.query(bounds))
                values=[(mapping(geometries[j]),codes.get(labels[j]['class_id'],labels[j]['class_id'])) for j in indices]
                a=rasterize(values,out_shape=(int(window.height),int(window.width)),transform=Affine.translation(window.col_off,window.row_off),dtype='uint16') if values else np.zeros((int(window.height),int(window.width)),np.uint16)
                valid=read_valid_mask(source,bands,window,missing_value,task.check)
                manual=[(mapping(geometries[j]),1) for j in indices if labels[j].get('editing_state')=='manual']
                if manual:
                    manual_mask=rasterize(manual,out_shape=a.shape,transform=Affine.translation(window.col_off,window.row_off),dtype='uint8').astype(bool)
                    valid |= manual_mask
                a[~valid]=65535;dst.write(a,1,window=window)
                task.signals.progress.emit(i+1,total,'导出原始网格标签…')
            dst.update_tags(codes='0=unlabeled;1..65534=label_value;65535=nodata',classes=json.dumps(classes or [],ensure_ascii=False),overlap_policy='non_overlapping_confirmed_labels',source=image['path'],smoothing_pixels=max((l.get('smoothing_applied',0) for l in labels),default=0))
    return str(path)
