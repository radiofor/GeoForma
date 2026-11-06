"""Reversible, bounded smoothing in source pixel coordinates; no model inference."""
import math
import numpy as np
from shapely.geometry import shape,mapping,Polygon,MultiPolygon,box
from shapely.ops import unary_union
from shapely.strtree import STRtree
from .contracts import finite_number
from .label_conflicts import polygonal_shape
from .label_context import same_image

DEFAULT_VALUE=1.0
MAX_VALUE=5.0


def settings(project,mode):
    return dict(project.get('smoothing',{}).get(mode,{'enabled':False,'value':DEFAULT_VALUE}))


def validate_settings(record):
    if not isinstance(record,dict) or type(record.get('enabled')) is not bool or not finite_number(record.get('value')) or not 1<=record['value']<=MAX_VALUE or record['value']!=int(record['value']):
        raise ValueError('平滑设置无效：强度必须为 1 至 5 的整数像素。')


def smoothing_sources(saved,draft,geometry):
    """Build identical smoothing inputs for restored and live workspaces."""
    from .editing_state import batch_labels
    sources=batch_labels(saved,draft)
    if geometry:
        sources=[label for label in sources if label['id']!=draft.get('base_id')]
        sources.append({'id':'__draft','geometry':geometry,'status':'draft'})
    return sources


def _ring(coordinates,value,task):
    points=np.asarray(coordinates,dtype=np.float64)[:,:2]
    segments=np.diff(points,axis=0);lengths=np.linalg.norm(segments,axis=1)
    keep=lengths>1e-10;starts=points[:-1][keep];segments=segments[keep];lengths=lengths[keep]
    if len(lengths)<3:return coordinates
    distance=np.r_[0.,np.cumsum(lengths)];perimeter=distance[-1]
    count=max(8,min(200000,int(math.ceil(perimeter/max(.5,value/2)))))
    positions=np.arange(count)*(perimeter/count)
    indices=np.minimum(np.searchsorted(distance,positions,side='right')-1,len(lengths)-1)
    sampled=starts[indices]+segments[indices]*((positions-distance[indices])/lengths[indices])[:,None]
    sigma=value/(perimeter/count);radius=min(60,max(1,int(math.ceil(3*sigma))))
    offsets=np.arange(-radius,radius+1);weights=np.exp(-.5*(offsets/max(sigma,1e-9))**2);weights/=weights.sum()
    result=np.zeros_like(sampled)
    for offset,weight in zip(offsets,weights):
        if task:task.check()
        result+=np.roll(sampled,int(offset),axis=0)*weight
    delta=result-sampled;movement=np.linalg.norm(delta,axis=1)
    result=sampled+delta*np.minimum(1.,value/np.maximum(movement,1e-12))[:,None]
    return np.vstack((result,result[0]))


def smooth_geometry(geometry,value=DEFAULT_VALUE,task=None):
    """Round stair steps without deleting components or interior rings."""
    validate_settings({'enabled':True,'value':value})
    return mapping(_smooth_shape(shape(geometry),value,task))


def _smooth_shape(original,value,task):
    parts=list(original.geoms) if original.geom_type=='MultiPolygon' else [original]
    result=[]
    for part in parts:
        if task:task.check()
        candidate=Polygon(_ring(part.exterior.coords,value,task),[_ring(r.coords,value,task) for r in part.interiors])
        # Strong smoothing must not erase a small pond or a narrow component.
        if not candidate.is_valid or candidate.area<part.area*.5 or any(Polygon(a).area<Polygon(b).area*.5 for a,b in zip(candidate.interiors,part.interiors)):
            candidate=part
        else:
            reduced=candidate.simplify(min(.05,value*.025),preserve_topology=True)
            if len(reduced.interiors)==len(part.interiors):candidate=reduced
        result.append(candidate)
    output=MultiPolygon(result) if original.geom_type=='MultiPolygon' else result[0]
    return output if output.is_valid else original


def smooth_batch(labels,value,image=None,task=None,cache=None,cache_epoch=None):
    return _smooth_batch(labels,value,image,task,cache,cache_epoch)


def _within_bounds(geometry,bounds):
    if geometry.is_empty:return True
    left,top,right,bottom=geometry.bounds
    return bounds[0]<=left and bounds[1]<=top and right<=bounds[2] and bottom<=bounds[3]


def _smooth_batch(labels,value,image,task,cache=None,cache_epoch=None):
    """Preserve each original footprint's ownership, then partition new overlaps."""
    records=list(labels)
    if not records:return []
    validate_settings({'enabled':True,'value':value})
    raw=[];outputs=[]
    extent_bounds=(0,0,image['width'],image['height']) if image else None
    extent=box(*extent_bounds) if extent_bounds else None
    order=sorted(range(len(records)),key=lambda i:(records[i].get('status')!='confirmed',i))
    completed={};tentative=[];epoch=(cache.snapshot() if cache_epoch is None else cache_epoch) if cache is not None else None
    # Resolve hits before inserting misses so a batch larger than the cache
    # cannot evict all reusable entries while scanning from the beginning.
    cached_shapes=[]
    if cache is not None:
        for i,label in enumerate(records):
            if task and i%128==0:task.check()
            cached_shapes.append(cache.get(label['geometry'],value,epoch))
    for i,label in enumerate(records):
        if task:task.check()
        source=label['geometry'];cached=cached_shapes[i] if cache is not None else None
        if cached is None:
            original=shape(source);g=_smooth_shape(original,value,task)
            if task:task.check()
            if cache is not None:cache.put(source,value,original,g,epoch)
        else:original,g=cached
        raw.append(original)
        if extent is not None and not _within_bounds(g,extent_bounds):g=g.intersection(extent)
        tentative.append(g)
    tree=STRtree(raw)
    expanded_tree=STRtree(tentative)
    for i in order:
        if task:task.check()
        g=tentative[i]
        # An adjacent small target always keeps its original territory.
        neighbors=[raw[int(j)] for j in tree.query(g,predicate='intersects') if int(j)!=i and same_image(records[i],records[int(j)]) and not (records[i].get('status')=='confirmed' and records[int(j)].get('status')!='confirmed') and raw[i].intersection(raw[int(j)]).area<=1e-9 and g.intersection(raw[int(j)]).area>0]
        neighbors.extend(completed[int(j)] for j in expanded_tree.query(g,predicate='intersects') if int(j) in completed and same_image(records[i],records[int(j)]) and g.intersection(completed[int(j)]).area>0)
        if neighbors:g=g.difference(unary_union(neighbors))
        g=polygonal_shape(g)
        if g is None:
            raise ValueError('平滑后目标为空，请减小平滑值。')
        geometry=mapping(g)
        completed[i]=g;outputs.append((i,dict(records[i],geometry=geometry,_bounds=list(g.bounds))))
    return [label for _,label in sorted(outputs)]


