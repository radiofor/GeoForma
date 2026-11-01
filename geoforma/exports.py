import json
from pathlib import Path
from .export_settings import DEFAULT_LABEL_FIELD
import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.transform import Affine
from shapely.geometry import shape,mapping,box
from shapely.strtree import STRtree
from .atomic_io import atomic_target


def protect_source(image,path):
    from .source_catalog import SourceGuard
    SourceGuard([image]).check(path)


def export_vector(image,labels,path,target_crs,task,classes=None,sources=None,label_field=DEFAULT_LABEL_FIELD):
    from .vector_export import write_vector
    from .raster import validate_grid
    validate_grid(image)
    from .source_catalog import SourceGuard
    guard=SourceGuard([image,*(sources or [])])
    return write_vector(image,labels,path,target_crs,task,classes,lambda image,target:guard.check(target),label_field=label_field)


def export_raster(image,labels,path,task,classes=None):
    from .label_conflicts import assert_no_overlaps
    from .raster import validate_grid
    validate_grid(image)
    assert_no_overlaps(labels,task)
    protect_source(image,path)
    if any(not isinstance(l.get('class_id'),int) or not 1<=l['class_id']<=65534 for l in labels):
        raise ValueError('标签栅格仅接受已赋予 1..65534 类别的区域；0 保留为未标注。')
    from .classes import class_values
    codes=class_values(classes or [])
    if classes is not None and any(label['class_id'] not in codes for label in labels):raise ValueError('导出标签引用了不存在的类别。')
    path=Path(path);transform=Affine(*image['transform'])
    crs=image.get('assigned_crs') or image['crs']
    if not crs:raise ValueError('请先指定影像 CRS。')
    geometries=[shape(l['geometry']) for l in labels];tree=STRtree(geometries)
    with atomic_target(path,suffix='.tif') as temp:
        with rasterio.open(image['path']) as source,rasterio.open(temp,'w',driver='GTiff',
            width=image['width'],height=image['height'],count=1,dtype='uint16',crs=crs,transform=transform,nodata=65535,
            tiled=True,blockxsize=512,blockysize=512,compress='deflate',BIGTIFF='IF_SAFER') as dst:
            from .nodata import declared_missing_value
            from .raster_validity import read_valid_mask
            missing_value=declared_missing_value(source)
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
