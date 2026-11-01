"""Optional single-component policy; source pixel edges, four-connectivity."""
from shapely.geometry import shape, mapping, Point


def select_polygon(geometry, points=()):
    if not geometry:return None
    g=shape(geometry)
    def parts(g):
        if g.geom_type=='Polygon':return [] if g.is_empty else [g]
        return [p for child in getattr(g,'geoms',()) for p in parts(child)]
    polygons=parts(g)
    if not polygons:return None
    if g.geom_type=='Polygon':return geometry
    positives=[Point(x,y) for x,y,label in points if label==1]
    # Stable input order breaks exact ties; keep holes and original boundaries.
    return mapping(max(polygons,key=lambda p:(sum(p.covers(q) for q in positives),p.area)))


def single_mask(mask, window, points):
    import numpy as np
    from rasterio.features import shapes, rasterize
    from rasterio.transform import Affine
    transform=Affine.translation(window[0],window[1])
    polygons=[g for g,_ in shapes(mask.astype(np.uint8),mask=mask,transform=transform,connectivity=4)]
    selected=select_polygon({'type':'GeometryCollection','geometries':polygons},points)
    if selected is None:return np.zeros_like(mask,dtype=bool)
    return rasterize([(selected,1)],out_shape=mask.shape,transform=transform,dtype='uint8').astype(bool)


def constrain_choice(choice,points=(),single=False,bounds=None):
    """The same contour policy at inference and desktop result boundaries."""
    from .prompt_bounds import clip_geometry
    geometry=clip_geometry(choice.get('geometry'),bounds)
    if single:geometry=select_polygon(geometry,points)
    if not geometry:return None
    if geometry is choice.get('geometry') and 'pixels' in choice:return choice
    return dict(choice,geometry=geometry,pixels=int(round(shape(geometry).area)))


def single_preview(bitmap,window,points=()):
    """Check connectivity on the displayed grid, with prompts scaled to that grid."""
    import numpy as np
    height,width=bitmap.shape
    scaled=[[(x-window[0])*width/window[2],(y-window[1])*height/window[3],label] for x,y,label in points]
    selected=single_mask(bitmap>0,[0,0,width,height],scaled)
    return np.where(selected,bitmap,0)


def preview_bitmap(mask,window,points=(),single=False,max_size=256):
    import numpy as np
    from PIL import Image
    height,width=mask.shape;scale=min(1.,max_size/max(width,height))
    size=(256,256) if max_size==256 else (max(1,round(width*scale)),max(1,round(height*scale)))
    bitmap=np.asarray(Image.fromarray(mask.astype(np.uint8)*255).resize(size,Image.Resampling.NEAREST)).copy()
    # Nearest-neighbor reduction can remove a one-pixel bridge in an otherwise
    # single full-resolution region; constrain the bitmap after resizing too.
    return single_preview(bitmap,window,points) if single else bitmap
