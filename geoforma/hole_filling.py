"""Fill polygon interiors and preview masks without touching other labels."""
from shapely.geometry import Polygon,shape
from shapely.ops import unary_union
from shapely.strtree import STRtree
from .label_context import same_image


def has_holes(geometry):
    """Check GeoJSON polygon rings without constructing a Shapely geometry."""
    coordinates=geometry.get('coordinates',()) if geometry else ()
    return (len(coordinates)>1 if geometry and geometry.get('type')=='Polygon' else
            any(len(polygon)>1 for polygon in coordinates) if geometry and geometry.get('type')=='MultiPolygon' else False)


def fill_label_holes(labels,task=None):
    """Derive filled views without changing labels or occupying another label.

    Smaller enclosing shells claim their holes first, so an inner annotation
    takes precedence over an outer annotation that surrounds it. Existing
    label footprints always retain ownership, independent of that ordering.
    """
    records=list(labels)
    if not records:return []
    if not any(has_holes(label['geometry']) for label in records):
        if task:task.check()
        return records
    originals=[];shells=[]
    for label in records:
        if task:task.check()
        raw=shape(label['geometry'])
        if raw.is_empty or not raw.is_valid or raw.geom_type not in ('Polygon','MultiPolygon'):
            raise ValueError('待填充的轮廓必须是有效多边形。')
        parts=list(raw.geoms) if raw.geom_type=='MultiPolygon' else [raw]
        shell=unary_union([Polygon(part.exterior) for part in parts]) if any(part.interiors for part in parts) else raw
        originals.append(raw);shells.append(shell)
    raw_tree=STRtree(originals);shell_tree=STRtree(shells)
    order=sorted(range(len(records)),key=lambda i:(records[i].get('status')!='confirmed',shells[i].area,i))
    added={};result=list(records)
    for i in order:
        if task:task.check()
        extra=shells[i].difference(originals[i])
        if extra.is_empty:continue
        occupied=[originals[int(j)] for j in raw_tree.query(extra,predicate='intersects') if int(j)!=i and same_image(records[i],records[int(j)])]
        occupied.extend(added[int(j)] for j in shell_tree.query(extra,predicate='intersects') if int(j) in added and same_image(records[i],records[int(j)]))
        if occupied:extra=extra.difference(unary_union(occupied))
        if extra.is_empty:continue
        filled=originals[i].union(extra)
        from .label_conflicts import polygonal
        geometry=polygonal(filled)
        if geometry is None:raise ValueError('填充后目标为空。')
        added[i]=extra
        record={key:value for key,value in records[i].items() if key not in ('_bounds','_render_path','_source_geometry','_source_path')}
        record['geometry']=geometry;result[i]=record
    return result


def fill_preview(bitmap):
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
    return np.where(filled,np.asarray(bitmap).max(),0).astype(np.asarray(bitmap).dtype)


