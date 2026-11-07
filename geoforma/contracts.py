"""Shared pixel-space and RGB contracts; backend feature payloads stay opaque."""
import math
from numbers import Real
from typing import Protocol,TypedDict

PixelWindow=tuple[int,int,int,int]
PixelPoint=tuple[float,float,int]


class RasterRecipe(TypedDict):
    bands:list[int]
    ranges:list[list[float]]
    format:str
    nodata_fill:int


class ModelBackend(Protocol):
    family:str
    execution:str
    config:dict
    schema:str
    streaming_preview:bool
    cache_bytes:int
    def load(self,config:dict,on_load=None)->None:...
    def key(self,image:dict,window:PixelWindow)->str:...
    def encode(self,image:dict,window:PixelWindow,rgb=None)->bool:...
    def restore(self,image:dict,window:PixelWindow)->bool:...
    def predict(self,image:dict,window:PixelWindow,rgb,valid,points,box=None,logits=None,seed=None,preview=False)->dict:...
    def close(self)->None:...


def finite_number(value):return isinstance(value,Real) and not isinstance(value,bool) and math.isfinite(value)


def validate_window(window,limit=None):
    if not isinstance(window,(list,tuple)) or len(window)!=4 or not all(finite_number(v) for v in window):raise ValueError('像元窗口必须包含四个有限数值。')
    x,y,w,h=map(int,window)
    if w<=0 or h<=0 or limit is not None and max(w,h)>limit:raise ValueError('像元窗口尺寸无效或超出允许范围。')
    return x,y,w,h


def validate_recipe(recipe,band_count=None):
    if not isinstance(recipe,dict):raise ValueError('尚未设置波段与拉伸。')
    bands=recipe.get('bands');ranges=recipe.get('ranges')
    if not isinstance(bands,(list,tuple)) or len(bands)!=3 or any(type(b) is not int or b<1 or band_count is not None and b>band_count for b in bands):raise ValueError('模型及显示输入必须选择三个有效波段，可重复选择单波段。')
    if not isinstance(ranges,(list,tuple)) or len(ranges)!=3 or any(not isinstance(r,(list,tuple)) or len(r)!=2 or not all(finite_number(v) for v in r) or r[1]<=r[0] for r in ranges):raise ValueError('波段拉伸范围必须为三个有限且递增的区间。')


def display_read_shape(window,max_size=None):
    """Main and reference displays use the same bounded allocation contract."""
    x,y,w,h=validate_window(window)
    if max_size is not None and (not finite_number(max_size) or max_size<=0):raise ValueError('显示读取尺寸必须为正数。')
    scale=min(1.,max_size/max(w,h)) if max_size else 1.
    output=(max(1,int(h*scale)),max(1,int(w*scale)))
    if output[0]*output[1]>8192**2:raise ValueError('读取窗口过大，请指定显示尺寸或使用分块读取。')
    return (x,y,w,h),output
