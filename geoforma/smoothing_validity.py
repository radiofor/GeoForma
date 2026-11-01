"""Read only mask tiles touched by outward smoothing, with bounded reuse."""
from collections import OrderedDict
from pathlib import Path
import math
import numpy as np
from shapely.geometry import box,shape
from shapely.ops import unary_union


class ValidSmoothing:
    def __init__(self,image,task):
        self.image=image or {};self.task=task;self.source=None;self.cache=OrderedDict()

    def __enter__(self):
        path=self.image.get('path')
        if path and Path(path).is_file():
            import rasterio
            from rasterio.enums import MaskFlags
            from .nodata import declared_missing_value
            source=rasterio.open(path)
            try:
                recipe=self.image.get('model_recipe') or self.image.get('display_recipe') or {}
                self.bands=recipe.get('bands') or [1]
                self.missing_value=declared_missing_value(source)
                self.floating=any(np.issubdtype(np.dtype(source.dtypes[b-1]),np.floating) for b in self.bands)
                if self.floating or self.missing_value is not None or any(MaskFlags.all_valid not in source.mask_flag_enums[b-1] for b in self.bands):self.source=source
                else:source.close()
            except BaseException:
                source.close();raise
        return self

    def __exit__(self,*args):
        if self.source is not None:self.source.close()

    def clip(self,geometry,original):
        if self.source is None:return geometry
        added=geometry.difference(original)
        if added.is_empty:return geometry
        from rasterio.windows import Window
        from rasterio.features import shapes
        from rasterio.transform import Affine
        x0,y0,x1,y1=added.bounds;blockers=[]
        for y in range(max(0,int(y0)//512*512),min(self.source.height,math.ceil(y1)),512):
            for x in range(max(0,int(x0)//512*512),min(self.source.width,math.ceil(x1)),512):
                if self.task:self.task.check()
                w,h=min(512,self.source.width-x),min(512,self.source.height-y)
                if not added.intersects(box(x,y,x+w,y+h)):continue
                key=(x,y)
                if key not in self.cache:
                    from .raster_validity import read_valid_mask
                    window=Window(x,y,w,h)
                    valid=read_valid_mask(self.source,self.bands,window,self.missing_value,self.task.check if self.task else None)
                    invalid=~valid
                    parts=[shape(g) for g,value in shapes(invalid.astype('uint8'),mask=invalid,transform=Affine.translation(x,y)) if value]
                    self.cache[key]=unary_union(parts) if parts else None
                    if len(self.cache)>16:self.cache.popitem(last=False)
                self.cache.move_to_end(key)
                if self.cache[key] is not None:blockers.append(self.cache[key])
        return geometry.difference(unary_union(blockers)) if blockers else geometry
