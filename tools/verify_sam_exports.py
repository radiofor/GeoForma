"""Verify every backend's masks through GeoForma's existing spatial export layer."""
import json,sys,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from main import configure_runtime
configure_runtime()
import numpy as np,rasterio
from rasterio.features import rasterize
from rasterio.transform import Affine
from rasterio.windows import Window
from geoforma.backend import mask_geometry
from geoforma.exports import export_vector,export_raster

class Silent:
    cancel_event=threading.Event()
    class signals:
        class progress:
            @staticmethod
            def emit(*a):pass
    def check(self):pass

def main():
    out=ROOT/'experiments/sam_versions';manifest=json.loads((out/'fixtures/manifest.json').read_text());results=[]
    for model in json.loads((out/'manifest.json').read_text())['models']:
        for provider,tag in [('low','L28_detail'),('high','L28_detail')]:
            key=provider+'_'+tag;file=out/'windows'/model['id']/'cuda'/(key+'.npz')
            if not file.exists():continue
            item=next(r for r in manifest['items'] if r['key']==key);image=next(r for r in manifest['images'] if Path(r['path'])==Path(item['source']));win=item['window']
            with np.load(file) as z:mask=z['refine']
            geom=mask_geometry(mask,win,image);assert geom
            rebuilt=rasterize([(geom,1)],out_shape=mask.shape,transform=Affine.translation(win[0],win[1])).astype(bool);assert np.array_equal(mask,rebuilt)
            directory=out/'exports'/model['id'];directory.mkdir(parents=True,exist_ok=True)
            label={'id':model['id']+'_'+key,'geometry':geom,'class_id':1,'status':'confirmed','source':'model_evaluation_only','model':{'variant':model['id']},'points':[[item['point'][0]+.5,item['point'][1]+.5,1]],'window':win}
            gpkg=directory/(key+'.gpkg');tif=directory/(key+'.tif');export_vector(image,[label],gpkg,'EPSG:4326',Silent());export_raster(image,[label],tif,Silent())
            with rasterio.open(tif) as ds:
                assert (ds.width,ds.height)==(image['width'],image['height']);assert ds.transform==Affine(*image['transform']);assert ds.crs.to_string()==image['crs'];actual=ds.read(1,window=Window(*win));assert np.array_equal(actual==1,mask)
                count=sum(int((ds.read(1,window=w)==1).sum()) for _,w in ds.block_windows(1));assert count==int(mask.sum())
            results.append({'model':model['id'],'fixture':key,'pixels':count,'mask_polygon_raster_exact':True,'original_grid_exact':True,'gpkg_reprojected':'EPSG:4326'});print(model['id'],key,'export exact',flush=True)
            (out/'export_verification.json').write_text(json.dumps(results,indent=2),encoding='utf-8')

if __name__=='__main__':main()
