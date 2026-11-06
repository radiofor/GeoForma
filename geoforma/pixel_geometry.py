"""Convert drawn contours to the same pixel-edge geometry as model masks."""
import math
import numpy as np
from rasterio.features import rasterize,shapes
from rasterio.transform import Affine
from shapely.geometry import box,mapping,shape
from shapely.ops import unary_union


def mask_geometry(mask,window,image,task=None,max_parts=None):
    """Trace a source-pixel mask into valid polygon geometry."""
    pixels=np.asarray(mask,dtype='uint8');transform=Affine.translation(window[0],window[1])
    pieces=[]
    for index,(geometry,_) in enumerate(shapes(pixels,mask=pixels.astype(bool),transform=transform,connectivity=4)):
        if task and index%256==0:task.check()
        if max_parts is not None and index>=max_parts:raise ValueError('多边形包含过多独立区域，请分段绘制。')
        pieces.append(shape(geometry))
    if not pieces:return None
    result=unary_union(pieces).intersection(box(0,0,image['width'],image['height']))
    if result.is_empty:return None
    # Clipping a pixel that only touches the image can produce a line or a
    # collection of lines and polygons.  Those boundary contacts have no
    # area and must never become label geometries.
    if result.geom_type=='GeometryCollection':
        polygons=[part for part in result.geoms if part.geom_type in ('Polygon','MultiPolygon') and part.area>0]
        if not polygons:return None
        result=polygons[0] if len(polygons)==1 else unary_union(polygons)
    elif result.geom_type not in ('Polygon','MultiPolygon') or result.area<=0:return None
    if not result.is_valid:
        raise ValueError('掩膜轮廓无效，未执行静默平滑或修复。')
    return mapping(result)


def pixel_contour(geometry,image,task=None):
    """Sample pixel centres, clipped to the source image, preserving components."""
    original=shape(geometry)
    if original.is_empty or not original.is_valid or original.geom_type not in ('Polygon','MultiPolygon'):
        raise ValueError('多边形无效，请调整顶点。')
    x0,y0,x1,y1=original.bounds
    x=max(0,math.floor(x0));y=max(0,math.floor(y0))
    right=min(image['width'],math.ceil(x1));bottom=min(image['height'],math.ceil(y1))
    width=right-x;height=bottom-y
    if width<=0 or height<=0:raise ValueError('多边形不包含影像像元，请调整范围。')
    if width*height>16_000_000:raise ValueError('多边形范围过大，请分段绘制。')
    if task:task.check()
    transform=Affine.translation(x,y)
    mask=rasterize([(mapping(original),1)],out_shape=(height,width),transform=transform,dtype='uint8')
    if not np.any(mask):raise ValueError('多边形未覆盖任何像元，请扩大绘制范围。')
    result=mask_geometry(mask,[x,y,width,height],image,task,max_parts=50000)
    if result is None:raise ValueError('多边形未覆盖任何像元，请扩大绘制范围。')
    if result['type'] not in ('Polygon','MultiPolygon'):raise ValueError('像元轮廓无效，请调整绘制范围。')
    return result
