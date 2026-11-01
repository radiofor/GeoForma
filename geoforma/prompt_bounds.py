"""Hard prompt box constraints in source pixel-edge coordinates."""
from shapely.geometry import shape,box as rectangle
from .label_conflicts import polygonal

MAX_PROMPT_POINTS=4096


def validate_points(points):
    from .contracts import finite_number
    if not isinstance(points,(list,tuple)):raise ValueError('提示点列表无效。')
    if len(points)>MAX_PROMPT_POINTS:raise ValueError('单个目标的提示点过多，请拆分目标。')
    for point in points:
        if not isinstance(point,(list,tuple)) or len(point)!=3 or not all(finite_number(v) for v in point[:2]) or type(point[2]) is not int or point[2] not in (0,1):
            raise ValueError('提示点必须包含有限像元坐标和正负类型。')


def contains_point(bounds,x,y):
    return bounds is None or bounds[0]<=x<=bounds[2] and bounds[1]<=y<=bounds[3]


def bounded_points(points,bounds):
    return [p for p in points if contains_point(bounds,p[0],p[1])]


def clip_geometry(geometry,bounds):
    if not geometry or bounds is None:return geometry
    return polygonal(shape(geometry).intersection(rectangle(*bounds)))


def bounded_mask(mask,window,bounds):
    if bounds is None:return mask
    import numpy as np
    # Keep pixels intersecting the box; exact geometry is clipped subsequently,
    # so fractional box edges retain their in-box pixel portions.
    x=np.arange(mask.shape[1])+window[0];y=np.arange(mask.shape[0])+window[1]
    return mask & ((x+1>bounds[0]) & (x<bounds[2]))[None,:] & ((y+1>bounds[1]) & (y<bounds[3]))[:,None]
