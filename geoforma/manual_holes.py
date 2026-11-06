"""Create an interior ring from a newly drawn polygon."""
import copy
from datetime import datetime
from shapely.geometry import mapping,shape


def create_hole(geometry,labels):
    """Return the containing saved label with a hole, or None for a normal label.

    Strict containment prevents a boundary-touching polygon from accidentally
    becoming a cut. Existing holes are excluded by the containment test.
    """
    hole=shape(geometry)
    if hole.geom_type not in ('Polygon','MultiPolygon') or hole.is_empty or not hole.is_valid:return None
    candidates=[]
    for label in labels:
        if label.get('status')!='confirmed':continue
        outer=shape(label['geometry'])
        if outer.contains(hole) and outer.boundary.disjoint(hole):
            candidates.append((outer.area,label,outer))
    if not candidates:return None
    _,label,outer=min(candidates,key=lambda item:item[0])
    result=outer.difference(hole)
    if result.is_empty or not result.is_valid or result.geom_type not in ('Polygon','MultiPolygon'):
        raise ValueError('无法创建有效的洞，请调整多边形后重试。')
    transient=('geometry','_bounds','_render_path','_source_geometry','_source_path',
               'raw_geometry','source_geometry','smoothing_applied','seed_geometry')
    updated=copy.deepcopy({key:value for key,value in label.items() if key not in transient})
    updated.update(geometry=mapping(result),editing_state='manual',edge=False)
    updated['manual_edits']=[*updated.get('manual_edits',[]),
                             {'tool':'draw_hole','at':datetime.now().isoformat()}]
    return updated
