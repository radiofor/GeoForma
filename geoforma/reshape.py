"""Local raster reshape. Human strokes define intent; no image edge search."""
import math
import numpy as np
from rasterio.features import rasterize,shapes
from rasterio.transform import Affine
from shapely.geometry import shape,mapping,LineString,Polygon,Point,box
from shapely.ops import substring,unary_union
from .label_conflicts import polygonal
from .single_polygon import select_polygon


def _intersection_points(geometry):
    if geometry.is_empty:return []
    if geometry.geom_type=='Point':return [geometry]
    if geometry.geom_type=='LineString':return [Point(geometry.coords[0]),Point(geometry.coords[-1])]
    return [point for part in getattr(geometry,'geoms',()) for point in _intersection_points(part)]


def _reshape_ring(boundary,hits,line,alternate):
    ordered=sorted(hits,key=line.project);first,last=ordered[0],ordered[-1]
    if line.project(last)-line.project(first)<=max(1.,line.length)*1e-12:raise ValueError('请穿过同一个边界至少两次。')
    replacement=list(substring(line,line.project(first),line.project(last)).coords)
    # Use identical intersection anchors, rather than independently rounded
    # linear-reference coordinates that can create microscopic self-crossings.
    replacement[0]=tuple(first.coords[0]);replacement[-1]=tuple(last.coords[0])
    a,b=boundary.project(first),boundary.project(last)
    if a>b:a,b=b,a;replacement.reverse()
    arc=list(substring(boundary,a,b).coords)
    complement=list(substring(boundary,b,boundary.length).coords)+list(substring(boundary,0,a).coords)[1:]
    arc[0]=replacement[0];arc[-1]=replacement[-1]
    complement[0]=replacement[-1];complement[-1]=replacement[0]
    # A stroke may enter and leave the same ring repeatedly. Only its first-to-
    # last intersection span participates. Discard invalid closing arcs instead
    # of rejecting a perfectly valid result on the other side of the stroke.
    choices=[(Polygon(arc+list(reversed(replacement))[1:]),LineString(arc).length),
             (Polygon(complement+replacement[1:]),LineString(complement).length)]
    choices=[(polygon,length) for polygon,length in choices if polygon.is_valid and not polygon.is_empty and polygon.area>0]
    if not choices:raise ValueError('编辑线无法形成有效边界，请调整编辑线。')
    choices.sort(key=lambda choice:(choice[1],choice[0].area),reverse=True)
    return choices[min(int(bool(alternate)),len(choices)-1)][0]


def reshape_intent(geometry,stroke,alternate=False):
    from .project_validation import validate_stroke
    validate_stroke(stroke)
    g=shape(geometry);line=LineString(stroke)
    if g.geom_type not in ('Polygon','MultiPolygon') or g.is_empty or not g.is_valid:raise ValueError('待重塑标签必须为有效多边形。')
    if not line.is_simple or not line.is_valid or line.length==0:raise ValueError('重塑线无效或自相交，请调整编辑线。')
    parts=list(g.geoms) if g.geom_type=='MultiPolygon' else [g];edited=[];touched=False
    for part in parts:
        rings=[part.exterior,*part.interiors];outlines=[Polygon(ring) for ring in rings]
        for index,ring in enumerate(rings):
            boundary=LineString(ring.coords);points=_intersection_points(line.intersection(boundary))
            if len(points)>=2:
                outlines[index]=_reshape_ring(boundary,points,line,alternate);touched=True
        outer=outlines[0];holes=outlines[1:]
        edited.append(outer.difference(unary_union(holes)) if holes else outer)
    if not touched:raise ValueError('请穿过同一个边界至少两次。')
    candidate=unary_union(edited);delta=g.symmetric_difference(candidate)
    if delta.is_empty:raise ValueError('编辑线没有改变轮廓。')
    x0,y0,x1,y1=delta.bounds
    window=[math.floor(x0)-1,math.floor(y0)-1,math.ceil(x1)-math.floor(x0)+2,math.ceil(y1)-math.floor(y0)+2]
    if window[2]*window[3]>16_000_000:raise ValueError('修改范围过大，请分段重塑。')
    return {'window':window,'original':geometry,'candidate':mapping(candidate),'stroke':stroke,'alternate':bool(alternate)}


def _geometry(mask,transform,task=None):
    polygons=[]
    for index,(g,_) in enumerate(shapes(mask.astype('uint8'),mask=mask,transform=transform,connectivity=4)):
        if index%256==0 and task:task.check()
        if index>=50000:raise ValueError('修改区的独立像元区域过多，请分段重塑。')
        polygons.append(shape(g))
    if task:task.check()
    return unary_union(polygons)


def reshape_patch(intent,image,valid=None,blockers=(),bounds=None,single=False,points=(),task=None):
    x,y,w,h=intent['window'];transform=Affine.translation(x,y)
    def burn(g):return rasterize([(g,1)],out_shape=(h,w),transform=transform,all_touched=False).astype(bool)
    original=shape(intent['original']);old=burn(intent['original']);new=burn(intent['candidate'])
    if task:task.check()
    add=new & ~old;remove=old & ~new
    xx=np.arange(w)+x;yy=np.arange(h)+y
    allowed=((xx>=0)&(xx<image['width']))[None,:]&((yy>=0)&(yy<image['height']))[:,None]
    if bounds:
        allowed &= ((xx>=math.ceil(bounds[0]))&(xx+1<=math.floor(bounds[2])))[None,:]&((yy>=math.ceil(bounds[1]))&(yy+1<=math.floor(bounds[3])))[:,None]
    if valid is not None:allowed &= valid
    if blockers:
        occupied=rasterize([(g,1) for g in blockers],out_shape=(h,w),transform=transform,all_touched=True).astype(bool)
        allowed &= ~occupied
    add &= allowed
    # Preserve holes untouched by the selected boundary, despite raster rounding.
    parts=list(original.geoms) if original.geom_type=='MultiPolygon' else [original]
    candidate=shape(intent['candidate']);candidate_parts=list(candidate.geoms) if candidate.geom_type=='MultiPolygon' else [candidate]
    candidate_holes=[Polygon(ring) for part in candidate_parts if part.geom_type=='Polygon' for ring in part.interiors]
    holes=[Polygon(ring) for part in parts for ring in part.interiors]
    protected=[hole for hole in holes if any(hole.equals(after) for after in candidate_holes)]
    if protected:add &= ~rasterize([(mapping(g),1) for g in protected],out_shape=(h,w),transform=transform,all_touched=True).astype(bool)
    added=_geometry(add,transform,task);removed=_geometry(remove,transform,task)
    result=original.difference(removed).union(added)
    if bounds:result=result.intersection(box(*bounds))
    resulting_parts=list(result.geoms) if result.geom_type=='MultiPolygon' else [result]
    resulting_holes=[Polygon(ring) for part in resulting_parts if part.geom_type=='Polygon' for ring in part.interiors]
    if any(not any(hole.equals(after) for after in resulting_holes) for hole in protected):raise ValueError('像元修改会改变未编辑的孔洞，请调整编辑线。')
    geometry=polygonal(result)
    if single:geometry=select_polygon(geometry,() if blockers else points)
    if not geometry:raise ValueError('框内没有可保留的轮廓，未执行重塑。')
    final=shape(geometry)
    if not final.is_valid:raise ValueError('像元重塑结果无效，未执行自动修复。')
    if final.equals(original):raise ValueError('编辑没有改变可用像元，请调整编辑线。')
    if blockers and any(final.intersection(shape(g)).area>0 for g in blockers):raise ValueError('已有标签存在重叠，请先处理原有重叠。')
    return {'geometry':geometry,'added_pixels':int(add.sum()),'removed_pixels':int(remove.sum()),'window':intent['window'],
            'stroke':intent['stroke'],'alternate':intent['alternate']}


def reshape_raster(image,geometry,stroke,blockers=(),bounds=None,single=False,points=(),alternate=False,task=None):
    from .raster import validate_source
    _,current=validate_source(image)
    if current!=image['fingerprint']:raise ValueError('影像源已变化，请重新导入后编辑。')
    if task:task.check();task.signals.progress.emit(0,0,'按像元网格重塑轮廓…')
    # Manual geometry is authoritative even where the raster has no data.
    intent=reshape_intent(geometry,stroke,alternate)
    if task:task.check()
    result=reshape_patch(intent,image,None,blockers,bounds,single,points,task)
    if task:task.check()
    return result
