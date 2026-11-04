"""Real Windows spawn, GPU feature reuse and vector/raster export acceptance."""
import argparse
import json
import os
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--weights-dir',type=Path,required=True);parser.add_argument('--device',default='cuda',choices=['cpu','cuda']);parser.add_argument('--all-models',action='store_true');parser.add_argument('--model');parser.add_argument('--output',type=Path);parser.add_argument('--single-polygon',action='store_true');args=parser.parse_args()
    from main import configure_runtime
    configure_runtime()
    import numpy as np,rasterio
    from shapely.geometry import shape
    from geoforma.atomic_io import atomic_json
    from geoforma.domain import new_project
    from geoforma.model_catalog import model_spec,MODELS
    from geoforma.raster import inspect_source,make_recipe
    from geoforma.inference.client import ModelService
    from geoforma.exports import export_vector,export_raster
    from geoforma.backend import mask_geometry
    out=(args.output or ROOT/'experiments/audit/modular'/args.device).resolve();out.mkdir(parents=True,exist_ok=True)
    os.environ['GEOFORMA_DATA_DIR']=str(out/'data' if args.output else ROOT/('build/modular_runtime_data_'+args.device))
    path=out/'model_input.tif';pixels=np.full((3,512,512),180,np.uint8);pixels[:,120:340,120:340]=np.array([30,90,120])[:,None,None]
    with rasterio.open(path,'w',driver='GTiff',width=512,height=512,count=3,dtype='uint8',crs='EPSG:32645',transform=rasterio.transform.from_origin(500000,3000000,2,2)) as ds:
        ds.write(pixels)
    image=inspect_source(path);image['model_recipe']=make_recipe(image,[1,2,3]);image['display_recipe']=image['model_recipe']
    previews=[]
    task=SimpleNamespace(cancel_event=threading.Event(),check=lambda:None,signals=SimpleNamespace(progress=SimpleNamespace(emit=lambda *a:None),preview=SimpleNamespace(emit=previews.append)))
    rows=[];service=ModelService()
    try:
        cases=[(s['backend'],s['variant']) for s in MODELS if args.all_models or s['id']==args.model] if args.all_models or args.model else [('sam','vit_b'),('sam2','tiny'),('sam2.1','small')]
        if not cases:raise ValueError('No matching registered model')
        for family,variant in cases:
            previews.clear()
            spec=model_spec(variant,family);checkpoint=args.weights_dir/spec['file']
            if not checkpoint.is_file():raise FileNotFoundError(checkpoint)
            config=dict(new_project()['model'],backend=family,variant=variant,device=args.device,execution='native',checkpoint=str(checkpoint))
            started=time.perf_counter();prepared=service.preprocess(image,config,[0,0,512,512],task)
            request={'window':[-128,-128,1024,1024],'points':[[200.5,200.5,1],[370.5,370.5,0]],'box':[80,80,400,400]}
            if args.single_polygon:request.update(single_polygon=True,points=request['points']+[[210.5,210.5,1],[230.5,230.5,1],[90.5,90.5,0]])
            result=service.predict(image,config,request,task);again=service.predict(image,config,request,task)
            assert result['device']==args.device and result['cache_hit'] and again['cache_hit'] and result['choices'] and again['choices']
            geometry=result['choices'][0]['geometry'];assert shape(geometry).equals(shape(again['choices'][0]['geometry']))
            if args.single_polygon:
                assert all(choice['geometry']['type']=='Polygon' for choice in result['choices']+again['choices'])
                assert previews
                for preview in previews:
                    h,w=preview['mask'].shape;visible=mask_geometry(preview['mask']>0,[0,0,w,h],{'width':w,'height':h})
                    assert visible is not None and visible['type']=='Polygon'
            label=dict(id=spec['id'],image_id=image['id'],class_id=1,status='confirmed',geometry=geometry)
            for suffix in ('gpkg','shp','geojson'):
                target=out/(spec['id']+'.'+suffix);export_vector(image,[label],target,'',task,classes=[{'id':1,'name':'Target'}]);assert target.exists()
            export_raster(image,[label],out/(spec['id']+'.tif'),task)
            with rasterio.open(out/(spec['id']+'.tif')) as ds:assert ds.width==512 and list(ds.transform)[:6]==image['transform']
            row={'model':spec['id'],'device':result['device'],'prepared_tiles':prepared['count'],'cache_reused':True,'single_polygon':args.single_polygon,'prompt_points':len(request['points']),'previews':len(previews),'exports':['gpkg','shp','geojson','tif'],'seconds':time.perf_counter()-started}
            rows.append(row);atomic_json(out/('runtime_'+args.device+'.json'),{'ok':True,'rows':rows},indent=2);print(json.dumps(row),flush=True)
    finally:service.close()


if __name__=='__main__':
    from multiprocessing import freeze_support
    freeze_support();main()
