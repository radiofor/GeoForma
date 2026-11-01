"""Exercise every registered adapter through the actual persistent model service."""
import argparse,json,os,sys,threading,time,copy
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from main import configure_runtime
configure_runtime()
from geoforma.model_catalog import MODELS
from geoforma.services import ModelService
from geoforma.raster import inspect_source,make_recipe
from geoforma.storage import save_project,load_project
from geoforma.domain import new_project
from geoforma.exports import export_vector,export_raster


def main():
    p=argparse.ArgumentParser();p.add_argument('--device',default='cuda');p.add_argument('--models',nargs='*');p.add_argument('--data-root',type=Path);p.add_argument('--output-dir',type=Path);args=p.parse_args()
    out=args.output_dir or ROOT/'experiments/model_integration'/'native'/args.device;out.mkdir(parents=True,exist_ok=True)
    os.environ['GEOFORMA_DATA_DIR']=str(args.data_root or out/'data')
    manifest=json.loads((ROOT/'experiments/sam_versions/manifest.json').read_text());weights={s['id']:s['path'] for s in manifest['models']}
    from geoforma.weights import default_checkpoint
    weights.setdefault('sam3_interactive',str(default_checkpoint('interactive','sam3')))
    fixture=json.loads((ROOT/'experiments/sam_versions/fixtures/manifest.json').read_text())['items']
    case=next(v for v in fixture if v['key']=='high_L28_detail')
    import numpy as np,rasterio
    with np.load(ROOT/'experiments/sam_versions/fixtures'/case['fixture']) as z:rgb=z['rgb'];valid=z['valid'];positive=z['positives'];negative=z['negatives'];box=z['box']
    tif=out/'input.tif'
    with rasterio.open(tif,'w',driver='GTiff',height=rgb.shape[0],width=rgb.shape[1],count=3,dtype='uint8',crs='EPSG:3857',transform=rasterio.transform.from_origin(0,1024,1,1)) as ds:
        ds.write(rgb.transpose(2,0,1));ds.write_mask(valid.astype(np.uint8)*255);ds.colorinterp=(rasterio.enums.ColorInterp.red,rasterio.enums.ColorInterp.green,rasterio.enums.ColorInterp.blue)
    image=inspect_source(tif);image['model_recipe']=make_recipe(image,[1,2,3]);window=[0,0,rgb.shape[1],rgb.shape[0]]
    points=[[float(x)+.5,float(y)+.5,1] for x,y in positive]+[[float(x)+.5,float(y)+.5,0] for x,y in negative]
    task=SimpleNamespace(cancel_event=threading.Event(),check=lambda:None,signals=SimpleNamespace(progress=SimpleNamespace(emit=lambda *a:None)))
    service=ModelService();rows=[]
    try:
        for spec in MODELS:
            if args.models and spec['id'] not in args.models:continue
            started=time.monotonic();config={'backend':spec['backend'],'variant':spec['variant'],'checkpoint':weights[spec['id']],'device':args.device,'execution':'auto'}
            prepared=service.preprocess(image,config,[0,0,image['width'],image['height']],task)
            request={'window':window,'points':points[:1]};first=service.predict(image,config,request,task);assert first['choices']
            request['points']=points;corrected=service.predict(image,config,request,task);assert corrected['choices'] and corrected['cache_hit']
            boxed=service.predict(image,config,{'window':window,'points':points,'box':box.tolist()},task);assert boxed['choices']
            seed=first['choices'][0]['geometry'];seeded=service.predict(image,config,{'window':window,'points':points,'seed':seed},task);assert seeded['choices']
            preview=service.preview(image,config,{'window':window,'points':points[:1]},task);assert preview is not None
            # A new model process must restore only this model's own multi-scale state.
            service.close();restored=service.predict(image,config,request,task)
            assert restored['cache_hit'] and restored['choices']
            from shapely.geometry import shape
            a=shape(restored['choices'][0]['geometry']);b=shape(corrected['choices'][0]['geometry'])
            assert a.intersection(b).area/a.union(b).area>=.99
            label={'id':spec['id'],'class_id':1,'image_id':image['id'],'status':'confirmed','geometry':corrected['choices'][0]['geometry'],'source':'test','model':config}
            folder=out/spec['id'];folder.mkdir(exist_ok=True);export_vector(image,[label],folder/'labels.gpkg','',task,[{'id':1,'name':'测试目标'}]);export_raster(image,[label],folder/'labels.tif',task,[{'id':1,'name':'测试目标'}])
            with rasterio.open(folder/'labels.tif') as ds:assert ds.width==image['width'] and ds.height==image['height'] and ds.transform==rasterio.transform.Affine(*image['transform'])
            row={'model':spec['id'],'ok':True,'full_preparation_tiles':prepared['count'],'fresh_cache_iou':a.intersection(b).area/a.union(b).area,'device':restored['device'],'schema':restored['model_metadata']['adapter'],'seconds':round(time.monotonic()-started,2)}
            rows.append(row);print(json.dumps(row),flush=True);(out/'results.json').write_text(json.dumps({'ok':True,'models':rows},indent=2))
    finally:service.close()


if __name__=='__main__':
    from multiprocessing import freeze_support
    freeze_support();main()
