"""Fill polygon interiors and preview masks without touching other labels."""
from shapely.geometry import Polygon,shape,mapping
from shapely.ops import unary_union


def fill_holes(geometry,blockers=()):
    if not geometry:return geometry
    original=shape(geometry)
    if original.is_empty or not original.is_valid or original.geom_type not in ('Polygon','MultiPolygon'):
        raise ValueError('待填充的轮廓必须是有效多边形。')
    parts=list(original.geoms) if original.geom_type=='MultiPolygon' else [original]
    if not any(part.interiors for part in parts):return geometry
    filled=unary_union([Polygon(part.exterior) for part in parts])
    occupied=[]
    for blocker in blockers:
        candidate=shape(blocker)
        if filled.intersects(candidate):occupied.append(candidate)
    if occupied:filled=filled.difference(unary_union(occupied))
    from .label_conflicts import polygonal
    result=polygonal(filled)
    if result is None:raise ValueError('填充后目标为空。')
    return result


def fill_preview(bitmap,valid=None):
    """Fill four-connected interior gaps in a small preview."""
    import numpy as np
    from PIL import Image,ImageDraw,ImageOps
    mask=np.asarray(bitmap)>0
    if mask.size==0 or not mask.any():return bitmap
    height,width=mask.shape
    transitions=np.count_nonzero(mask[:,1:]!=mask[:,:-1])+np.count_nonzero(mask[1:,:]!=mask[:-1,:])
    if transitions<=4096:
        from rasterio.features import shapes,rasterize
        background=(~mask).astype('uint8');holes=[]
        for geometry,_ in shapes(background,mask=background.astype(bool),connectivity=4):
            boundary=geometry['coordinates'][0]
            if not any(x<=0 or y<=0 or x>=width or y>=height for x,y in boundary):holes.append((geometry,1))
        filled=mask | rasterize(holes,out_shape=mask.shape).astype(bool) if holes else mask.copy()
    else:
        image=ImageOps.expand(Image.fromarray(mask.astype('uint8')*255),border=1,fill=0)
        ImageDraw.floodfill(image,(0,0),128)
        filled=np.asarray(image)[1:-1,1:-1]!=128
    if valid is not None:
        allowed=np.asarray(Image.fromarray(np.asarray(valid,dtype='uint8')).resize((width,height),Image.Resampling.NEAREST),dtype=bool)
        filled &= allowed
    return np.where(filled,np.asarray(bitmap).max(),0).astype(np.asarray(bitmap).dtype)


def fill_prediction(geometry,valid,window):
    """Fill holes without adding model pixels outside the valid raster mask."""
    import numpy as np
    filled=fill_holes(geometry)
    if filled is geometry or np.asarray(valid,dtype=bool).all():return filled
    from rasterio.features import rasterize,shapes
    from rasterio.transform import Affine
    allowed=np.asarray(valid,dtype=bool);transform=Affine.translation(window[0],window[1])
    added=shape(filled).difference(shape(geometry))
    invalid=(~allowed)&rasterize([(mapping(added),1)],out_shape=allowed.shape,transform=transform,dtype='uint8').astype(bool)
    if not invalid.any():return filled
    excluded=unary_union([shape(item) for item,_ in shapes(invalid.astype('uint8'),mask=invalid,transform=transform,connectivity=4)])
    from .label_conflicts import polygonal
    return polygonal(shape(filled).difference(excluded))


def fill_reshape_result(result,blockers=()):
    geometry=result['geometry'];filled=fill_holes(geometry,blockers)
    if filled is geometry:return result
    added=max(0,round(shape(filled).area-shape(geometry).area))
    return dict(result,geometry=filled,added_pixels=result['added_pixels']+added)
