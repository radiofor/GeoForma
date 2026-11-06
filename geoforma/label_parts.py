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


def split_resolved_label(label,original_geometry,identifiers=(),part_classes=None):
    """Keep draft identities and classes attached to their original components.

    The resolved geometry must be a subset of the original. Clipping can
    change component sizes, remove a component or split it, so match the
    resolved geometry to each original component before assigning IDs.
    """
    classes=part_classes or {}
    if original_geometry['type']=='Polygon':
        # A single source component cannot exchange identity with another.
        # Avoid a costly intersection and preserve unchanged ring ordering.
        return split_label(dict(label,class_id=classes.get(label['id'],label['class_id'])))
    from .label_conflicts import polygonal
    original=dict(label,geometry=original_geometry)
    resolved=shape(label['geometry']);records=[]
    for part in split_label(original,identifiers):
        geometry=polygonal(shape(part['geometry']).intersection(resolved))
        if geometry is None:continue
        part.update(geometry=geometry,class_id=classes.get(part['id'],label['class_id']))
        records.extend(split_label(part))
    return records
