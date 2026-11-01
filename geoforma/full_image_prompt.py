"""A fixed, bounded image frame for interactive SAM, independent of click positions."""
from .contracts import display_read_shape

# Keep normal training tiles at their original resolution. Larger rasters use
# one bounded overview, so clicks never enlarge/re-encode a moving crop.
MAX_SIDE=2048


def frame(image):
    bounds=[0,0,image['width'],image['height']]
    _,(height,width)=display_read_shape(bounds,MAX_SIDE)
    sx=width/image['width'];sy=height/image['height']
    a,b,c,d,e,f=image['transform']
    proxy=dict(image,width=width,height=height,
               transform=[a/sx,b/sy,c,d/sx,e/sy,f],_preview_size=1024)
    return proxy,[0,0,width,height],bounds,sx,sy


def geometry_scale(geometry,sx,sy):
    if geometry is None or sx==sy==1:return geometry
    from shapely.geometry import shape,mapping
    from shapely.affinity import scale
    return mapping(scale(shape(geometry),xfact=sx,yfact=sy,origin=(0,0)))
