"""Explicit polygon conflict policy in source pixel coordinates; no smoothing."""
from shapely.geometry import shape,mapping,MultiPolygon
from shapely.ops import unary_union
from shapely.strtree import STRtree


def polygonal(geometry):
    if geometry.is_empty:return None
    if not geometry.is_valid:raise ValueError('标签几何无效，未执行自动修复。')
    if geometry.geom_type in ('Polygon','MultiPolygon'):return mapping(geometry)
    if geometry.geom_type!='GeometryCollection':return None
    parts=[]
    for part in geometry.geoms:
        result=polygonal(part)
        if result:
            g=shape(result);parts.extend(list(g.geoms) if g.geom_type=='MultiPolygon' else [g])
    return mapping(MultiPolygon(parts)) if parts else None


def others(label,labels):
    return [l for l in labels if l['status']=='confirmed' and l['image_id']==label['image_id'] and l['id']!=label['id']]


def conflicts(label,labels):
    g=shape(label['geometry'])
    if g.is_empty or not g.is_valid:raise ValueError('当前轮廓无效，无法保存。')
    candidates=others(label,labels)
    if not candidates:return []
    geometries=[shape(l['geometry']) for l in candidates];tree=STRtree(geometries)
    return [candidates[int(i)] for i in tree.query(g) if g.intersection(geometries[int(i)]).area>0]


def resolve(label,labels,policy='clip'):
    if policy not in ('clip','merge'):raise ValueError('未知重叠处理方式。')
    g=shape(label['geometry']);original_area=g.area;removed=[];remaining=others(label,labels)
    if g.is_empty or not g.is_valid:raise ValueError('当前轮廓无效，无法保存。')
    geometries=[shape(l['geometry']) for l in remaining];tree=STRtree(geometries);removed_indices=set()
    def intersecting():
        return [int(j) for j in tree.query(g) if int(j) not in removed_indices and g.intersection(geometries[int(j)]).area>0]
    if policy=='merge':
        # Include every connected same-class overlap, including chains.
        while True:
            joined=[j for j in intersecting() if remaining[j]['class_id']==label['class_id']]
            if not joined:break
            g=unary_union([g,*[geometries[j] for j in joined]])
            removed.extend(remaining[j] for j in joined);removed_indices.update(joined)
    indices=intersecting();blockers=[remaining[j] for j in indices]
    if blockers:g=g.difference(unary_union([geometries[j] for j in indices]))
    geometry=polygonal(g)
    return {'geometry':geometry,'removed':removed,'blocked_ids':[l['id'] for l in blockers],
            'original_area':original_area,'saved_area':g.area,'policy':policy}


def assert_no_overlaps(labels,task=None,geometries=None):
    confirmed=[l for l in labels if l['status']=='confirmed']
    if geometries is None:geometries=[shape(l['geometry']) for l in confirmed]
    elif len(geometries)!=len(confirmed):raise ValueError('重叠检查的标签与几何数量不一致。')
    tree=STRtree(geometries)
    for i,g in enumerate(geometries):
        if task:task.check()
        for j in tree.query(g):
            j=int(j)
            if j>i and confirmed[i]['image_id']==confirmed[j]['image_id'] and g.intersection(geometries[j]).area>0:
                raise ValueError(f"已保存标签存在重叠：{confirmed[i]['id'][:8]} 与 {confirmed[j]['id'][:8]}。请调整并重新保存后导出。")
