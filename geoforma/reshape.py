"""Reshape canonical polygon geometry using human-drawn strokes."""
import math
import numpy as np
from rasterio.features import rasterize,shapes
from rasterio.transform import Affine
from shapely.geometry import shape,mapping,LineString,MultiLineString,Polygon,Point,box
from shapely.ops import substring,unary_union,nearest_points
from shapely.strtree import STRtree
from .single_polygon import select_polygon
from .reshape_validity import repair_reshape_geometry


class ReshapeNoChange(ValueError):
    """The requested edit leaves the contour unchanged."""
    def __init__(self,message,blocked_geometry=None):
        super().__init__(message)
        self.blocked_geometry=blocked_geometry


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
    # Repair each closing arc independently. A repeated crossing can make the
    # longer (intended) side invalid while the tiny opposite side is valid;
    # discarding it would silently replace the whole label with that tiny side.
    choices=[]
    for ring,length in ((arc,LineString(arc).length),(complement,LineString(complement).length)):
        points=ring+(list(reversed(replacement))[1:] if ring is arc else replacement[1:])
        try:polygon=repair_reshape_geometry(Polygon(points))
        except ValueError:continue
        choices.append((polygon,length))
    if not choices:raise ValueError('编辑线无法形成有效边界，请调整编辑线。')
    choices.sort(key=lambda choice:(choice[1],choice[0].area),reverse=True)
    return choices[min(int(bool(alternate)),len(choices)-1)][0]


def editable_boundary(geometry,include_holes=True):
    """Only visible rings may be picked when holes are filled for display."""
    polygon=shape(geometry) if isinstance(geometry,dict) else geometry
    if include_holes:return polygon.boundary
    parts=polygon.geoms if polygon.geom_type=='MultiPolygon' else (polygon,)
    rings=[part.exterior.coords for part in parts]
    return LineString(rings[0]) if len(rings)==1 else MultiLineString(rings)


def reshape_intent(geometry,stroke,alternate=False,include_holes=True):
    from .project_validation import validate_stroke
    validate_stroke(stroke)
    g=shape(geometry);line=LineString(stroke)
    if g.geom_type not in ('Polygon','MultiPolygon') or g.is_empty or not g.is_valid:raise ValueError('待重塑标签必须为有效多边形。')
    if not line.is_simple or not line.is_valid or line.length==0:raise ValueError('重塑线无效或自相交，请调整编辑线。')
    parts=list(g.geoms) if g.geom_type=='MultiPolygon' else [g];edited=[];touched=False
    for part in parts:
        rings=[part.exterior,*part.interiors];outlines=[Polygon(ring) for ring in rings]
        outer_points=_intersection_points(line.intersection(LineString(part.exterior.coords)))
        outer_edit=len(outer_points)>=2 and max(map(line.project,outer_points))-min(map(line.project,outer_points))>max(1.,line.length)*1e-12
        for index,ring in enumerate(rings):
            # An outer edit clips the existing holes. Independently editing a
            # crossed hole would fill or enlarge the surviving part of it.
            if index and (not include_holes or outer_edit):continue
            boundary=LineString(ring.coords);points=outer_points if index==0 else _intersection_points(line.intersection(boundary))
            if len(points)>=2:
                outlines[index]=_reshape_ring(boundary,points,line,alternate);touched=True
        outer=outlines[0];holes=outlines[1:]
        edited.append(outer.difference(unary_union(holes)) if holes else outer)
    if not touched:raise ValueError('请穿过同一个边界至少两次。')
    return _candidate_intent(geometry,stroke,alternate,g,unary_union(edited))


def _candidate_intent(geometry,stroke,alternate,g,candidate):
    candidate=repair_reshape_geometry(candidate);delta=g.symmetric_difference(candidate)
    if delta.is_empty:raise ReshapeNoChange('编辑线没有改变轮廓。')
    x0,y0,x1,y1=delta.bounds
    window=[math.floor(x0)-1,math.floor(y0)-1,math.ceil(x1)-math.floor(x0)+2,math.ceil(y1)-math.floor(y0)+2]
    if window[2]*window[3]>16_000_000:raise ValueError('修改范围过大，请分段重塑。')
    return {'window':window,'original':geometry,'candidate':mapping(candidate),'stroke':stroke,'alternate':bool(alternate)}


def _match_polygons(originals,views):
    """Match rings by overlapping area, rejecting ambiguous correspondences."""
    if len(originals)!=len(views):raise ValueError('平滑轮廓与原始轮廓不匹配，请调整编辑线。')
    if not originals:return []
    tree=STRtree(originals);used=set();result=[]
    for view in views:
        scored=[]
        for index in tree.query(view,predicate='intersects'):
            i=int(index);area=view.intersection(originals[i]).area
            if area>1e-12:scored.append((area,i))
        scored.sort(reverse=True)
        if not scored or (len(scored)>1 and abs(scored[0][0]-scored[1][0])<=max(1.,scored[0][0])*1e-10):
            raise ValueError('平滑轮廓与原始轮廓不匹配，请调整编辑线。')
        match=scored[0][1]
        if match in used:raise ValueError('平滑轮廓与原始轮廓不匹配，请调整编辑线。')
        used.add(match);result.append(match)
    return result


def reshape_reference_intent(geometry,reference,stroke,alternate=False,include_holes=True):
    """Transfer a stroke on a smoothed outline to its corresponding raw rings.

    Only the edited arcs are replaced; the rest of the raw geometry and its
    interior rings remain authoritative for subsequent display and undo.
    """
    from .project_validation import validate_stroke
    validate_stroke(stroke)
    raw=shape(geometry);shown=shape(reference);line=LineString(stroke)
    if not line.is_simple or not line.is_valid or not line.length:raise ValueError('重塑线无效或自相交，请调整编辑线。')
    if raw.geom_type not in ('Polygon','MultiPolygon') or not raw.is_valid or shown.geom_type!=raw.geom_type or not shown.is_valid:
        raise ValueError('平滑轮廓与原始轮廓不匹配，请调整编辑线。')
    originals=list(raw.geoms) if raw.geom_type=='MultiPolygon' else [raw]
    views=list(shown.geoms) if shown.geom_type=='MultiPolygon' else [shown]
    paired=_match_polygons([Polygon(part.exterior) for part in originals], [Polygon(part.exterior) for part in views])
    edited=[];touched=False
    for view,part_index in zip(views,paired):
        part=originals[part_index]
        raw_holes=list(part.interiors);view_holes=list(view.interiors)
        outer_hits=_intersection_points(line.intersection(LineString(view.exterior.coords)))
        outer_edit=len(outer_hits)>=2 and max(map(line.project,outer_hits))-min(map(line.project,outer_hits))>max(1.,line.length)*1e-12
        hole_pairs=(_match_polygons([Polygon(ring) for ring in raw_holes], [Polygon(ring) for ring in view_holes])
                    if include_holes and not outer_edit else [])
        rings=[part.exterior,*[raw_holes[index] for index in hole_pairs]];visible=[view.exterior,*view_holes] if include_holes and not outer_edit else [view.exterior]
        outlines=[Polygon(ring) for ring in rings]
        for index,(ring,display_ring) in enumerate(zip(rings,visible)):
            if index and (not include_holes or outer_edit):continue
            boundary=LineString(ring.coords);hits=outer_hits if index==0 else _intersection_points(line.intersection(LineString(display_ring.coords)))
            if len(hits)<2:continue
            ordered=sorted(hits,key=line.project);first,last=ordered[0],ordered[-1]
            if line.project(last)-line.project(first)<=max(1.,line.length)*1e-12:continue
            anchors=[nearest_points(boundary,p)[0] for p in (first,last)]
            if anchors[0].distance(anchors[1])<=1e-10:raise ValueError('平滑轮廓与原始轮廓不匹配，请调整编辑线。')
            segment=list(substring(line,line.project(first),line.project(last)).coords)
            transferred=LineString([tuple(anchors[0].coords[0]),*segment,tuple(anchors[1].coords[0])])
            if not transferred.is_simple:raise ValueError('编辑线无法匹配原始轮廓，请调整编辑线。')
            outlines[index]=_reshape_ring(boundary,anchors,transferred,alternate);touched=True
        holes=outlines[1:] if include_holes and not outer_edit else [Polygon(ring) for ring in raw_holes]
        edited.append(outlines[0].difference(unary_union(holes)) if holes else outlines[0])
    if not touched:raise ValueError('请穿过同一个边界至少两次。')
    return _candidate_intent(geometry,stroke,alternate,raw,unary_union(edited))


def _geometry(mask,transform,task=None):
    polygons=[]
    for index,(g,_) in enumerate(shapes(mask.astype('uint8'),mask=mask,transform=transform,connectivity=4)):
        if index%256==0 and task:task.check()
        if index>=50000:raise ValueError('修改区的独立像元区域过多，请分段重塑。')
        polygons.append(shape(g))
    if task:task.check()
    return unary_union(polygons)


def _polygon_parts(geometry):
    if geometry.geom_type=='Polygon':return [geometry]
    return [part for child in getattr(geometry,'geoms',()) for part in _polygon_parts(child)]


def _orthogonal_lines(geometry):
    if geometry.is_empty or geometry.geom_type in ('Point','MultiPoint'):return True
    if geometry.geom_type in ('LineString','LinearRing'):
        return all(abs(a[0]-b[0])<1e-9 or abs(a[1]-b[1])<1e-9
                   for a,b in zip(geometry.coords,list(geometry.coords)[1:]))
    return all(_orthogonal_lines(part) for part in getattr(geometry,'geoms',()))


def reshape_patch(intent,image,valid=None,blockers=(),bounds=None,single=False,task=None,pixel_grid=False):
    """Apply the edit to the current vector, clipping additions to permitted areas."""
    x,y,w,h=intent['window'];transform=Affine.translation(x,y)
    original=shape(intent['original']);candidate=shape(intent['candidate'])
    if task:task.check()
    # Only labels touching the added region can constrain it. Unioning every
    # annotation on an image makes a small local edit unnecessarily expensive.
    blocker_shapes=[]
    for index,geometry in enumerate(blockers):
        if task and index%128==0:task.check()
        blocker_shapes.append(shape(geometry))
    if pixel_grid:
        # Only edit the changed pixel cells.  Keeping the original outside
        # those cells preserves existing contours and interior rings.
        def burn(g):return rasterize([(mapping(g),1)],out_shape=(h,w),transform=transform,all_touched=False).astype(bool)
        old=burn(original);new=burn(candidate)
        added=new & ~old;removed_centres=old & ~new
        # A fractional hole or clipped edge can leave original polygon pieces
        # in cells whose centres were already outside the old mask.  Include
        # cells touched by the actual removal so these pieces cannot survive
        # as detached remnants when that region is cut away.
        removal=original.difference(candidate)
        touched=(rasterize([(mapping(removal),1)],out_shape=(h,w),transform=transform,all_touched=True).astype(bool)
                 if not removal.is_empty else np.zeros_like(old))
        extra=touched & ~new & ~old
        retained=original.intersection(candidate)
        partials=[];original_boundary_guard=None
        if extra.any() and not retained.is_empty:
            # Most residual cells are far from retained geometry.  Use a
            # raster broad phase and exact areas only at ambiguous boundaries.
            retained_touched=rasterize([(mapping(retained),1)],out_shape=(h,w),transform=transform,all_touched=True).astype(bool)
            for row,col in zip(*np.nonzero(extra & retained_touched)):
                if task:task.check()
                cell=box(x+int(col),y+int(row),x+int(col)+1,y+int(row)+1)
                piece=removal.intersection(cell)
                if piece.area<=0:extra[row,col]=False;continue
                if retained.intersection(cell).area>0:
                    extra[row,col]=False
                    # Preserve both portions without introducing a new
                    # diagonal into a pixel contour.  Exact orthogonal cuts
                    # can safely remove just their actual fraction.
                    area_piece=unary_union(_polygon_parts(piece))
                    if original_boundary_guard is None:original_boundary_guard=original.boundary.buffer(1e-9)
                    if _orthogonal_lines(area_piece.boundary.difference(original_boundary_guard)):
                        partials.append(area_piece)
                    else:raise ValueError('小数边界与编辑线无法安全匹配，请调整编辑线。')
        removed=removed_centres | extra
        xs=np.arange(x,x+w);ys=np.arange(y,y+h)
        permitted=(ys[:,None]>=0)&(ys[:,None]<image['height'])&(xs[None,:]>=0)&(xs[None,:]<image['width'])
        if bounds:
            permitted &= (xs[None,:]>=bounds[0])&(ys[:,None]>=bounds[1])&(xs[None,:]+1<=bounds[2])&(ys[:,None]+1<=bounds[3])
        if valid is not None:permitted &= np.asarray(valid,dtype=bool)
        added &= permitted
        blocked=None
        if blocker_shapes and added.any():
            rows=np.flatnonzero(added.any(axis=1));cols=np.flatnonzero(added.any(axis=0))
            addition_bounds=box(x+int(cols[0]),y+int(rows[0]),x+int(cols[-1])+1,y+int(rows[-1])+1)
            nearby=[g for g in blocker_shapes if g.intersects(addition_bounds)]
            # all_touched provides candidates only; exact area tests allow
            # two annotations to touch along an edge without overlap.
            if nearby:
                touched=rasterize([(mapping(g),1) for g in nearby],out_shape=(h,w),transform=transform,all_touched=True).astype(bool)
                tree=STRtree(nearby)
                excluded=np.zeros_like(added)
                for row,col in zip(*np.nonzero(added & touched)):
                    if task:task.check()
                    cell=box(x+int(col),y+int(row),x+int(col)+1,y+int(row)+1)
                    if any(cell.intersection(nearby[int(i)]).area>0 for i in tree.query(cell,predicate='intersects')):
                        added[row,col]=False;excluded[row,col]=True
                if excluded.any():blocked=mapping(_geometry(excluded,transform,task))
        if not added.any() and not removed_centres.any():raise ReshapeNoChange('编辑未改变任何像元，请扩大编辑范围。',blocked)
        result=original
        if removed.any():result=result.difference(_geometry(removed,transform,task))
        if partials:result=result.difference(unary_union(partials))
        if added.any():result=result.union(_geometry(added,transform,task))
        if result.geom_type=='MultiPolygon':
            # Any piece with no area in the intended result is a residual of
            # the cut, not an unrelated retained component.
            parts=[part for part in result.geoms if part.intersection(candidate).area>0]
            result=unary_union(parts)
        final=repair_reshape_geometry(result)
        if single:final=repair_reshape_geometry(select_polygon(mapping(final),()))
        if any(final.intersects(g) and final.intersection(g).area>0 for g in blocker_shapes):
            raise ValueError('已有标签存在重叠，请先处理原有重叠。')
        if final.equals(original):raise ReshapeNoChange('编辑未改变任何像元，请扩大编辑范围。',blocked)
        return {'geometry':mapping(final),'added_pixels':int(added.sum()),'removed_pixels':int(removed_centres.sum()),
                'window':intent['window'],'stroke':intent['stroke'],'alternate':intent['alternate'],'_blocked_geometry':blocked}
    addition=candidate.difference(original)
    allowed=box(0,0,image['width'],image['height'])
    if bounds:
        allowed=allowed.intersection(box(*bounds))
    if valid is not None:
        allowed=allowed.intersection(_geometry(np.asarray(valid,dtype=bool),transform,task))
    blocked=None
    if blocker_shapes and not addition.is_empty:
        nearby=[g for g in blocker_shapes if g.intersects(addition)]
        if nearby:
            occupied=unary_union(nearby);excluded=addition.intersection(occupied)
            if not excluded.is_empty and excluded.area>0:blocked=mapping(excluded)
            allowed=allowed.difference(occupied)
    # Cuts and unchanged rings come from the current geometry alone. In
    # particular, an earlier hole cannot be reintroduced by raster rounding.
    result=original.intersection(candidate).union(addition.intersection(allowed))
    if bounds:result=result.intersection(box(*bounds))
    if task:task.check()
    final=repair_reshape_geometry(result)
    if single:final=repair_reshape_geometry(select_polygon(mapping(final),()))
    if final.equals(original):raise ReshapeNoChange('编辑没有改变轮廓，请调整编辑线。',blocked)
    if any(final.intersects(g) and final.intersection(g).area>0 for g in blocker_shapes):
        raise ValueError('已有标签存在重叠，请先处理原有重叠。')
    # Pixel counts remain diagnostic metadata; the vector result never depends
    # on whether a subpixel change happens to cover a pixel centre.
    def burn(g):return rasterize([(mapping(g),1)],out_shape=(h,w),transform=transform,all_touched=False).astype(bool)
    old=burn(original);new=burn(final)
    return {'geometry':mapping(final),'added_pixels':int((new & ~old).sum()),
            'removed_pixels':int((old & ~new).sum()),'window':intent['window'],
            'stroke':intent['stroke'],'alternate':intent['alternate'],'_blocked_geometry':blocked}


def validate_reshape_source(image,task=None):
    """Verify the shared raster before and after a batch of edits."""
    if task:task.check()
    from .raster import validate_source
    _,current=validate_source(image)
    if current!=image['fingerprint']:raise ValueError('影像源已变化，请重新导入后编辑。')
    if task:task.check()


def reshape_geometry(image,geometry,stroke,blockers=(),bounds=None,single=False,alternate=False,task=None,include_holes=True,reference=None,pixel_grid=False):
    """Compute one edit after the caller has verified the raster source."""
    if task:task.check()
    # Manual geometry is authoritative even where the raster has no data.
    intent=reshape_reference_intent(geometry,reference,stroke,alternate,include_holes) if reference is not None else reshape_intent(geometry,stroke,alternate,include_holes)
    if task:task.check()
    result=reshape_patch(intent,image,None,blockers,bounds,single,task,pixel_grid)
    if task:task.check()
    return result


def reshape_raster(image,geometry,stroke,blockers=(),bounds=None,single=False,alternate=False,task=None,include_holes=True,reference=None,pixel_grid=False):
    """Validate the raster and compute a single edit."""
    validate_reshape_source(image,task)
    if task:task.signals.progress.emit(0,0,'重塑轮廓…')
    return reshape_geometry(image,geometry,stroke,blockers,bounds,single,alternate,task,include_holes,reference,pixel_grid)
