"""Compact authority and full projection name for independent metadata rows."""
from functools import lru_cache


@lru_cache(maxsize=128)
def describe_crs(value):
    if not value:return '—','—'
    try:
        from osgeo import osr
        osr.UseExceptions()
        reference=osr.SpatialReference();reference.SetFromUserInput(value)
        authority=reference.GetAuthorityName(None);code=reference.GetAuthorityCode(None)
        return (f'{authority}:{code}' if authority and code else '自定义坐标系',reference.GetName() or '—')
    except Exception:return value,'—'
