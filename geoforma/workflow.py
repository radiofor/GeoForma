"""Full-raster preparation policy; independent of view coordinates and Qt controls."""
from collections import deque
from pathlib import Path
import math,shutil
from .domain import digest

CORE=768

def full_bounds(image):return [0,0,image['width'],image['height']]

def tile_count(image):return math.ceil(image['width']/CORE)*math.ceil(image['height']/CORE)

def prompt_misses(geometry,points):
    """Engineering selection heuristic; this is not a semantic quality score."""
    from shapely.geometry import shape,Point
    region=shape(geometry)
    return sum(region.covers(Point(x,y))!=(label==1) for x,y,label in points)

def best_choice(choices,points):
    if not choices:return -1
    return min(range(len(choices)),key=lambda i:(prompt_misses(choices[i]['geometry'],points),-choices[i]['score']))

def preparation_signature(image,model):
    path=Path(model['checkpoint'])
    stamp=[str(path.resolve()),path.stat().st_size,path.stat().st_mtime_ns] if path.is_file() else [str(path),None,None]
    return digest({'schema':'full_preparation_v1','source':image.get('fingerprint'),'grid':[image['width'],image['height'],image.get('transform')],
        'recipe':image.get('model_recipe'),'backend':model.get('backend','sam'),'variant':model['variant'],'weights':stamp})

def fully_prepared(image,model):
    return bool(image.get('ready') and image.get('prepared_full_signature')==preparation_signature(image,model))


def preparation_window(images,current):
    """Only the selected image and its immediate successor, without wrapping."""
    if current is None:return ()
    index=next((i for i,image in enumerate(images) if image['id']==current['id']),None)
    return tuple(images[index:index+2]) if index is not None else ()

def check_cache_space(root,count,bytes_per_block=4*1024*1024):
    if count==0:return 0
    root=Path(root);root.mkdir(parents=True,exist_ok=True);free=shutil.disk_usage(root).free
    reserve=max(1024**3,min(10*1024**3,free//10));required=count*(bytes_per_block+16384)
    if required>free-reserve:
        raise RuntimeError(f'缓存空间不足：完整影像约需 {required/1024**3:.1f} GiB，可用 {free/1024**3:.1f} GiB。释放缓存所在磁盘的空间后继续准备。')
    return required

class PreparationQueue:
    def __init__(self):self.ids=deque();self.paused=False
    def add(self,identifiers):
        for identifier in identifiers:
            if identifier not in self.ids:self.ids.append(identifier)
    def replace(self,identifiers):self.ids=deque(dict.fromkeys(identifiers))
    def next(self,project):
        if self.paused:return None
        while self.ids:
            identifier=self.ids.popleft();image=next((i for i in project['images'] if i['id']==identifier),None)
            if image is None or fully_prepared(image,project['model']):continue
            if not image.get('model_recipe'):image['preparation_state']='bands_required';continue
            return image
        return None
    def reset(self):self.ids.clear();self.paused=False
