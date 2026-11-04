from __future__ import annotations

from pathlib import Path
from stat import S_ISREG
import numpy as np
import rasterio
from rasterio.windows import Window
from rasterio.enums import Resampling

from .domain import digest, uid


def _source_fingerprint(names):
    files=[]
    for name in sorted(names):
        path=Path(name)
        try:stamp=path.stat()
        except OSError as error:raise FileNotFoundError(f"影像或 VRT 引用不可访问：{name}") from error
        if not S_ISREG(stamp.st_mode):raise FileNotFoundError(f"影像或 VRT 引用不可访问：{name}")
        files.append((str(path.resolve()),stamp.st_size,stamp.st_mtime_ns))
    return digest(files)


def fingerprint(source):
    with rasterio.open(source) as ds:return _source_fingerprint(ds.files)


def inspect_source(path):
    path = str(Path(path).resolve())
    with rasterio.open(path) as ds:
        source_files=ds.files;stamp=_source_fingerprint(source_files)
        colors = [c.name for c in ds.colorinterp]
        rgb = [colors.index(c)+1 for c in ("red", "green", "blue")] if all(c in colors for c in ("red", "green", "blue")) else None
        if ds.count == 1:
            rgb = [1, 1, 1]
        return {"id": uid(), "path": path, "name": Path(path).name, "width": ds.width, "height": ds.height,
                "bands": ds.count, "dtypes": list(ds.dtypes), "colors": colors, "crs": ds.crs.to_string() if ds.crs else "",
                "assigned_crs": "", "transform": list(ds.transform)[:6], "nodata": ds.nodata if ds.nodata is None or np.isfinite(ds.nodata) else "NaN",
                "fingerprint": stamp, "model_recipe": None, "display_recipe": None,
                "suggested_bands": rgb, "ready": False, "source_files": len(source_files),
                "source_paths": [str(Path(name).resolve()) for name in source_files]}


def make_recipe(image, bands,minimum_span=1.,relative_span=0.,missing_value=None):
    with rasterio.open(image["path"]) as ds:
        from .nodata import declared_missing_value,tagged_recipe
        if missing_value is None:missing_value=declared_missing_value(ds)
        scale = min(1, 768/max(ds.width, ds.height))
        if len(bands)!=3 or any(type(b) is not int or not 1<=b<=ds.count for b in bands):raise ValueError('请选择三个有效波段。')
        ranges = {};sample_shape=(max(1,int(ds.height*scale)),max(1,int(ds.width*scale)))
        for band in dict.fromkeys(bands):
            array=ds.read(band,out_shape=sample_shape,masked=True)
            if missing_value is not None:array=np.ma.masked_equal(array,missing_value)
            valid = array.compressed()
            valid = valid[np.isfinite(valid)]
            if not len(valid):
                if missing_value is not None:ranges[band]=[0.,1.];continue
                raise ValueError("采样区域没有有效像元，无法确定拉伸范围。")
            if array.dtype == np.uint8:
                ranges[band]=[0., 255.]
            else:
                lo, hi = np.percentile(valid, [2, 98]); ranges[band]=[float(lo), float(max(hi, lo+max(minimum_span,abs(lo)*relative_span)))]
    return tagged_recipe({"bands": list(bands), "ranges": [ranges[b] for b in bands], "format": "RGB uint8", "nodata_fill": 0},missing_value)


def mark_recipe_policy(image,recipe):
    from .nodata import declared_missing_value,tagged_recipe
    with rasterio.open(image['path']) as source:missing_value=declared_missing_value(source)
    return tagged_recipe(recipe,missing_value)


def read_rgb(image, window, recipe=None, max_size=None):
    from .contracts import validate_recipe,display_read_shape
    recipe = recipe or image.get("model_recipe")
    validate_recipe(recipe)
    (x,y,w,h),output_shape=display_read_shape(window,max_size)
    out=np.zeros((*output_shape,3),np.uint8);valid=np.zeros(output_shape,bool)
    # Sequential unique-band reads bound memory and support mixed-dtype VRT bands.
    from contextlib import ExitStack
    from .nodata import declared_missing_value
    from rasterio.vrt import WarpedVRT
    with ExitStack() as stack:
        source=stack.enter_context(rasterio.open(image["path"]))
        missing_value=declared_missing_value(source)
        ds=stack.enter_context(WarpedVRT(source,src_nodata=missing_value,nodata=missing_value,transform=source.transform,width=source.width,height=source.height,resampling=Resampling.bilinear)) if missing_value is not None else source
        validate_recipe(recipe,ds.count)
        left,top=max(0,x),max(0,y);right,bottom=min(ds.width,x+w),min(ds.height,y+h)
        if right>left and bottom>top:
            ox0,oy0=round((left-x)*output_shape[1]/w),round((top-y)*output_shape[0]/h)
            ox1,oy1=round((right-x)*output_shape[1]/w),round((bottom-y)*output_shape[0]/h)
            if ox1>ox0 and oy1>oy0:
                read_window=Window(left,top,right-left,bottom-top);size=(oy1-oy0,ox1-ox0)
                area=np.s_[oy0:oy1,ox0:ox1];valid[area]=True
                for band in dict.fromkeys(recipe['bands']):
                    if missing_value is not None:
                        masked=ds.read(band,window=read_window,out_shape=size,masked=True,resampling=Resampling.bilinear if max_size else Resampling.nearest)
                        data=masked.astype('float32').filled(float('nan'))
                        valid[area] &= ~np.ma.getmaskarray(masked) & np.isfinite(data)
                    else:
                        data=ds.read(band,window=read_window,out_shape=size,
                            resampling=Resampling.bilinear if max_size else Resampling.nearest)
                        valid[area] &= (ds.read_masks(band,window=read_window,out_shape=size)>0) & np.isfinite(data)
                    rendered={}
                    for channel,selected in enumerate(recipe['bands']):
                        if selected!=band:continue
                        lo,hi=recipe['ranges'][channel]
                        if (lo,hi) in rendered:
                            out[oy0:oy1,ox0:ox1,channel]=out[oy0:oy1,ox0:ox1,rendered[(lo,hi)]]
                            continue
                        values=data.astype(np.float32)
                        np.nan_to_num(values,copy=False,nan=lo,posinf=hi,neginf=lo)
                        np.subtract(values,lo,out=values);np.multiply(values,255./(hi-lo),out=values)
                        np.clip(values,0,255,out=values)
                        out[oy0:oy1,ox0:ox1,channel]=values.astype(np.uint8)
                        rendered[(lo,hi)]=channel
                        del values
                    del data
    out[~valid]=0
    return out,valid


def validate_grid_dataset(source,image):
    """Validate an already open dataset, returning its declared missing value."""
    from .nodata import declared_missing_value
    if source.width != image["width"] or source.height != image["height"] or list(source.transform)[:6] != image["transform"] or (source.crs.to_string() if source.crs else '') != image['crs']:
        raise ValueError("原始影像网格已改变，不能安全复用此项目的像元标签。")
    return declared_missing_value(source)


def validate_grid(image):
    with rasterio.open(image["path"]) as ds:
        return validate_grid_dataset(ds,image)


def validate_source(image):
    """Check the grid and compute the source fingerprint with one dataset open."""
    with rasterio.open(image['path']) as ds:
        missing=validate_grid_dataset(ds,image)
        return missing,_source_fingerprint(ds.files)
