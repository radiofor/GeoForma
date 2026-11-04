"""Reversible, bounded smoothing in source pixel coordinates; no model inference."""
import math
import numpy as np
from shapely.geometry import shape,mapping,Polygon,MultiPolygon,box
from shapely.ops import unary_union
from shapely.strtree import STRtree
from .contracts import finite_number
from .label_conflicts import polygonal

DEFAULT_VALUE=1.0
MAX_VALUE=5.0


def settings(project,mode):
    return dict(project.get('smoothing',{}).get(mode,{'enabled':False,'value':DEFAULT_VALUE}))


def validate_settings(record):
    if not isinstance(record,dict) or type(record.get('enabled')) is not bool or not finite_number(record.get('value')) or not 1<=record['value']<=MAX_VALUE or record['value']!=int(record['value']):
        raise ValueError('平滑设置无效：强度必须为 1 至 5 的整数像素。')


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
    original=shape(geometry);parts=list(original.geoms) if original.geom_type=='MultiPolygon' else [original]
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
    return mapping(output) if output.is_valid else geometry


def smooth_batch(labels,value,image=None,task=None):
    from .smoothing_validity import ValidSmoothing
    with ValidSmoothing(image,task) as validity:return _smooth_batch(labels,value,image,task,validity)


def _smooth_batch(labels,value,image,task,validity):
    """Preserve each original footprint's ownership, then partition new overlaps."""
    records=list(labels)
    if not records:return []
    raw=[shape(l['geometry']) for l in records];tree=STRtree(raw);outputs=[]
    extent=box(0,0,image['width'],image['height']) if image else None
    order=sorted(range(len(records)),key=lambda i:(records[i].get('status')!='confirmed',i))
    completed={};tentative=[]
    for i,label in enumerate(records):
        if task:task.check()
        g=shape(smooth_geometry(label['geometry'],value,task))
        if extent is not None:g=g.intersection(extent)
        if label.get('box') and label.get('editing_state')!='manual':g=g.intersection(box(*label['box']))
        g=validity.clip(g,raw[i])
        tentative.append(g)
    expanded_tree=STRtree(tentative)
    for i in order:
        if task:task.check()
        g=tentative[i]
        # An adjacent small target always keeps its original territory.
        neighbors=[raw[int(j)] for j in tree.query(g) if int(j)!=i and not (records[i].get('status')=='confirmed' and records[int(j)].get('status')!='confirmed') and raw[i].intersection(raw[int(j)]).area<=1e-9 and g.intersection(raw[int(j)]).area>0]
        neighbors.extend(completed[int(j)] for j in expanded_tree.query(g) if int(j) in completed and g.intersection(completed[int(j)]).area>0)
        if neighbors:g=g.difference(unary_union(neighbors))
        geometry=polygonal(g)
        if geometry is None:
            raise ValueError('平滑后目标为空，请减小平滑值。')
        g=shape(geometry)
        if records[i].get('model',{}).get('single_polygon') and g.geom_type=='MultiPolygon':
            g=max(g.geoms,key=lambda p:p.area);geometry=mapping(g)
        completed[i]=g;outputs.append((i,dict(records[i],geometry=geometry,_bounds=list(g.bounds))))
    return [label for _,label in sorted(outputs)]


def stored_labels(project,task=None):
    """Materialize the selected mode options for a project file, preserving sources."""
    images={im['id']:im for im in project['images']};result=[dict(l) for l in project['labels']]
    for label in result:
        if 'source_geometry' in label:label['geometry']=label.pop('source_geometry');label.pop('smoothing_applied',None)
    groups={}
    for i,label in enumerate(result):
        image=images[label['image_id']];mode='individual';config=settings(project,mode)
        if config['enabled']:groups.setdefault((image['id'],mode),[]).append(i)
    for (image_id,mode),indices in groups.items():
        config=settings(project,mode);confirmed=[i for i in indices if result[i]['status']=='confirmed']
        from .smoothing_validity import ValidSmoothing
        with ValidSmoothing(images[image_id],task) as validity:
            derived=_smooth_batch([result[i] for i in confirmed],config['value'],images[image_id],task,validity)
            for i,label in zip(confirmed,derived):
                result[i]={**label,'source_geometry':result[i]['geometry'],'smoothing_applied':config['value']};result[i].pop('_bounds',None)
    return result
