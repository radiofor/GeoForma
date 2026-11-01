"""Store disconnected polygon components as independently addressable labels."""
import copy
from shapely.geometry import shape,mapping
from .domain import uid


def split_label(label,identifiers=()):
    geometry=shape(label['geometry'])
    if geometry.geom_type=='Polygon':return [label]
    if geometry.geom_type!='MultiPolygon':raise ValueError('标签必须为有效多边形。')
    # Retain the original identity on the largest component. Holes belong to
    # their containing polygon and never become separate labels.
    parts=sorted(geometry.geoms,key=lambda part:(-part.area,part.bounds))
    records=[]
    for index,part in enumerate(parts):
        record=copy.deepcopy({k:v for k,v in label.items() if k not in
            ('geometry','raw_geometry','source_geometry','smoothing_applied','_bounds','_render_path','_source_geometry','_source_path')})
        record.update(id=label['id'] if index==0 else identifiers[index] if index<len(identifiers) else uid(),geometry=mapping(part))
        records.append(record)
    return records
