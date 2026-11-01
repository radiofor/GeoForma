"""Read-only label presentation; independent of generation settings and Qt."""
from shapely.geometry import shape,mapping
from shapely.ops import unary_union
from shapely.strtree import STRtree


def partition_labels(labels,blockers=(),task=None):
    from .label_conflicts import polygonal
    ordered=sorted(labels,key=lambda l:(l.get('source') not in ('prompt_guided','ai_reviewed_draft'),
                   bool(l.get('edge')),-(l.get('score') or 0),shape(l.get('raw_geometry') or l['geometry']).area,l['id']))
    shapes=[]
    for label in ordered:
        if task:task.check()
        shapes.append(shape(label.get('raw_geometry') or label['geometry']))
    tree=STRtree(shapes)
    saved=[shape(l['geometry']) for l in blockers];saved_tree=STRtree(saved);result=[]
    for index,(label,geometry) in enumerate(zip(ordered,shapes)):
        if task:task.check()
        covers=[shapes[int(j)] for j in tree.query(geometry) if int(j)<index]
        covers.extend(saved[int(j)] for j in saved_tree.query(geometry))
        clipped=geometry.difference(unary_union(covers)) if covers else geometry
        polygon=polygonal(clipped)
        if polygon is None:continue
        unchanged=clipped.equals(shape(label['geometry']))
        item=dict(label,geometry=label['geometry'] if unchanged else polygon)
        if covers:
            item['raw_geometry']=label.get('raw_geometry') or label['geometry']
            item['overlap_policy']='partition'
        if not unchanged:
            for field in ('_render_path','_source_path','_source_geometry'):item.pop(field,None)
        item['_bounds']=list(clipped.bounds);result.append(item)
    return result


class LabelIndex:
    def __init__(self,labels,width=None,height=None,task=None):
        saved=[label for label in labels if label['status']=='confirmed']
        shapes=[]
        for label in saved:
            if task:task.check()
            shapes.append(shape(label['geometry']))
        tree=STRtree(shapes);self.confirmed=[]
        for index,(label,geometry) in enumerate(zip(saved,shapes)):
            if task:task.check()
            covers=[shapes[int(j)] for j in tree.query(geometry) if int(j)>index]
            clipped=geometry.difference(unary_union(covers)) if covers else geometry
            if not clipped.is_empty:
                unchanged=clipped.equals(geometry)
                item=dict(label,geometry=label['geometry'] if unchanged else mapping(clipped),_bounds=list(clipped.bounds))
                if not unchanged:
                    for field in ('_render_path','_source_path','_source_geometry'):item.pop(field,None)
                self.confirmed.append(item)
        self.candidates=partition_labels([l for l in labels if l['status']=='candidate'],saved,task)
        self.by_id={label['id']:label for label in self.confirmed+self.candidates}
        self._visible_cache={}

    def visible(self,draft=None):
        geometry=draft.get('geometry') if draft else None;base=draft.get('base_id') if draft else None
        key=(id(geometry),base);cached=self._visible_cache.get(key)
        if cached and cached[0] is geometry:return cached[1]
        saved=self.confirmed;candidates=self.candidates
        if geometry:
            active=shape(geometry)
            candidates=[label for label in candidates if label['id']!=base and shape(label['geometry']).intersection(active).area<=1e-8]
            saved=[]
            for label in self.confirmed:
                if label['id']==base:continue
                source=shape(label['geometry']);clipped=source.difference(active)
                if not clipped.is_empty:
                    if clipped.equals(source):saved.append(label)
                    else:
                        item=dict(label,geometry=mapping(clipped),_bounds=list(clipped.bounds))
                        for field in ('_render_path','_source_path','_source_geometry'):item.pop(field,None)
                        saved.append(item)
        result=(saved,candidates)
        if len(self._visible_cache)>2:self._visible_cache.clear()
        self._visible_cache[key]=(geometry,result);return result


def vertex_count(geometry):
    coordinates=geometry.get('coordinates',())
    polygons=(coordinates,) if geometry.get('type')=='Polygon' else coordinates
    return sum(len(ring) for polygon in polygons for ring in polygon)
