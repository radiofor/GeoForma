"""Read-only label presentation; independent of generation settings and Qt."""
from shapely.geometry import shape,mapping
from shapely.ops import unary_union
from shapely.strtree import STRtree


class LabelIndex:
    def __init__(self,labels,task=None):
        saved=[label for label in labels if label['status']=='confirmed']
        shapes=[];vertices=0
        for label in saved:
            if task:task.check()
            vertices+=vertex_count(label['geometry'])
            shapes.append(shape(label['geometry']))
        self.cache_weight=len(saved)*512+vertices*128
        tree=STRtree(shapes);self.confirmed=[];self._geometries=[];unchanged_index=True
        for index,(label,geometry) in enumerate(zip(saved,shapes)):
            if task:task.check()
            # Shared edges and corners do not remove any area. Avoid building
            # unions and differences for dense grids of touching labels.
            covers=[shapes[int(j)] for j in tree.query(geometry,predicate='intersects')
                    if int(j)>index and geometry.relate_pattern(shapes[int(j)],'T********')]
            clipped=geometry.difference(unary_union(covers)) if covers else geometry
            if not clipped.is_empty:
                unchanged=not covers or clipped.equals(geometry)
                item=dict(label,geometry=label['geometry'] if unchanged else mapping(clipped),_bounds=list(clipped.bounds))
                if not unchanged:
                    unchanged_index=False
                    for field in ('_render_path','_source_path','_source_geometry'):item.pop(field,None)
                self.confirmed.append(item)
                self._geometries.append(clipped)
            else:unchanged_index=False
        if unchanged_index:self._geometries=shapes;self._tree=tree
        else:self._tree=STRtree(self._geometries)
        self._visible_cache={}

    def visible(self,draft=None):
        geometry=draft.get('geometry') if draft else None;base=draft.get('base_id') if draft else None
        key=(id(geometry),base);cached=self._visible_cache.get(key)
        if cached and cached[0] is geometry:return cached[1]
        saved=self.confirmed
        if geometry:
            active=shape(geometry)
            affected={int(i) for i in self._tree.query(active,predicate='intersects')
                      if self._geometries[int(i)].relate_pattern(active,'T********')}
            saved=[]
            for index,label in enumerate(self.confirmed):
                if label['id']==base:continue
                if index not in affected:
                    saved.append(label);continue
                source=self._geometries[index];clipped=source.difference(active)
                if not clipped.is_empty:
                    if clipped.equals(source):saved.append(label)
                    else:
                        item=dict(label,geometry=mapping(clipped),_bounds=list(clipped.bounds))
                        for field in ('_render_path','_source_path','_source_geometry'):item.pop(field,None)
                        saved.append(item)
        if len(self._visible_cache)>2:self._visible_cache.clear()
        self._visible_cache[key]=(geometry,saved);return saved


def vertex_count(geometry):
    coordinates=geometry.get('coordinates',())
    polygons=(coordinates,) if geometry.get('type')=='Polygon' else coordinates
    return sum(len(ring) for polygon in polygons for ring in polygon)
