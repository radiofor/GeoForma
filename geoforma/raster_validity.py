"""Read one consistent validity mask for raster-derived operations."""
import numpy as np


def read_valid_mask(source,bands,window,missing_value=None,check=None):
    """Combine native per-band masks, non-finite values and explicit missing values."""
    bands=list(dict.fromkeys(bands))
    if not bands:raise ValueError('影像没有可检查的波段。')
    valid=None
    for band in bands:
        if check:check()
        mask=source.read_masks(band,window=window)>0
        if valid is None:valid=mask
        else:valid &= mask
        floating=np.issubdtype(np.dtype(source.dtypes[band-1]),np.floating)
        if not floating and missing_value is None:continue
        values=source.read(band,window=window)
        if floating:valid &= np.isfinite(values)
        if missing_value is not None:valid &= values!=missing_value
    return valid
