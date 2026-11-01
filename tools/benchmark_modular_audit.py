"""Compare current hot paths with the local pre-audit source snapshot."""
import gc
import json
from pathlib import Path
import statistics
import sys
import time
import tracemalloc
import types

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def legacy(name):
    module=types.ModuleType('geoforma._audit_'+name);module.__package__='geoforma'
    exec((ROOT/'build/modular_audit_before/geoforma'/f'{name}.py').read_text(encoding='utf-8-sig'),module.__dict__)
    return module


def measure(call):
    times=[];peak=0;result=None
    for _ in range(3):
        gc.collect();tracemalloc.start();start=time.perf_counter();result=call()
        times.append(time.perf_counter()-start);peak=max(peak,tracemalloc.get_traced_memory()[1]);tracemalloc.stop()
    return result,{'median_seconds':statistics.median(times),'peak_traced_mib':peak/1024**2}


def main():
    from main import configure_runtime
    configure_runtime()
    import numpy as np,rasterio
    from shapely.geometry import box,mapping,shape
    from geoforma.raster import inspect_source,read_rgb
    from geoforma.label_conflicts import resolve
    out=ROOT/'experiments/audit/modular';out.mkdir(parents=True,exist_ok=True)
    raster=out/'memory_input.tif';rng=np.random.default_rng(7)
    with rasterio.open(raster,'w',driver='GTiff',width=2048,height=2048,count=3,dtype='float32',crs='EPSG:3857',transform=rasterio.transform.from_origin(0,2048,1,1)) as ds:
        for band in range(1,4):
            data=rng.random((2048,2048),dtype=np.float32);data[0,:]=np.nan;ds.write(data,band)
    image=inspect_source(raster);image['model_recipe']={'bands':[1,2,3],'ranges':[[0.,1.]]*3}
    old=legacy('raster');expected,before=measure(lambda:old.read_rgb(image,[0,0,2048,2048]));actual,after=measure(lambda:read_rgb(image,[0,0,2048,2048]))
    assert all(np.array_equal(a,b) for a,b in zip(actual,expected))
    report={'raster':{'identical_pixels':True,'before':before,'after':after,'peak_reduction_percent':100*(1-after['peak_traced_mib']/before['peak_traced_mib'])}}
    labels=[dict(id=str(i),status='confirmed',image_id='image',class_id=1,geometry=mapping(box(i*20,0,i*20+10,10))) for i in range(4000)]
    label=dict(id='new',image_id='image',class_id=1,geometry=mapping(box(5,0,15,10)))
    old=legacy('label_conflicts')
    def old_save():old.conflicts(label,labels);return old.resolve(label,labels)
    expected,before=measure(old_save);actual,after=measure(lambda:resolve(label,labels))
    assert shape(expected['geometry']).equals(shape(actual['geometry'])) and expected['blocked_ids']==actual['blocked_ids']
    report['conflict_save']={'labels':len(labels),'identical_geometry':True,'before':before,'after':after,'speedup':before['median_seconds']/after['median_seconds']}
    (out/'performance.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report),flush=True)


if __name__=='__main__':main()
