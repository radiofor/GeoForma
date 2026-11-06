"""Repair the polygonal output of a reshape without retaining old geometry."""
from shapely import make_valid
from shapely.geometry import shape
from shapely.ops import unary_union


def repair_reshape_geometry(value):
    """Return a nonempty valid Polygon/MultiPolygon, discarding non-area remnants."""
    geometry=shape(value) if isinstance(value,dict) else value
    if geometry.is_empty:raise ValueError('重塑结果没有可保留的多边形。')
    if geometry.is_valid and geometry.geom_type in ('Polygon','MultiPolygon'):
        return geometry
    repaired=make_valid(geometry) if not geometry.is_valid else geometry
    def polygons(item):
        if item.geom_type=='Polygon':
            if not item.is_empty and item.area>0:yield item
        else:
            for child in getattr(item,'geoms',()):yield from polygons(child)
    parts=list(polygons(repaired))
    if not parts:raise ValueError('重塑结果没有可保留的多边形。')
    result=parts[0] if len(parts)==1 else unary_union(parts)
    if result.is_empty or not result.is_valid or result.geom_type not in ('Polygon','MultiPolygon'):
        raise ValueError('重塑结果无法修复为有效多边形。')
    return result
