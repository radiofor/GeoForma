"""Read explicitly declared, otherwise unflagged raster missing values."""
import math,re


def declared_missing_value(source):
    if source.count!=1 or source.nodata is not None:return None
    tag=source.tags().get('missing_value_encoding','')
    match=re.fullmatch(r'\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s+stored as ordinary values;\s*no TIFF NoData or mask\s*',tag,re.IGNORECASE)
    if not match:return None
    # A real mask takes precedence over the tag's claim that no mask exists.
    # Overriding it with src_nodata would otherwise discard its invalid pixels.
    from rasterio.enums import MaskFlags
    if MaskFlags.all_valid not in source.mask_flag_enums[0]:return None
    value=float(match.group(1))
    return value if math.isfinite(value) else None


def tagged_recipe(recipe,missing_value):
    """Include the validity policy in feature cache keys and project signatures."""
    result=dict(recipe)
    if missing_value is not None:result['validity_policy']={'kind':'declared_missing_v1','value':missing_value}
    return result
