"""Freeze native-resolution RGB and identical prompts for every official SAM backend."""
import json,sys,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import numpy as np
from geoforma.raster import inspect_source,make_recipe,read_rgb

def main():
    out=ROOT/'experiments/sam_versions/fixtures';out.mkdir(parents=True,exist_ok=True)
    inventory=json.loads((ROOT/'experiments/lake_review/inventory.json').read_text())
    images={};rows=[]
    for item in inventory:
        path=item['source']
        if path not in images:
            image=inspect_source(path);image['model_recipe']=make_recipe(image,[1,2,3]);images[path]=image
        image=images[path];x,y=item['point'];n=1024;win=[x-n//2,y-n//2,n,n]
        rows.append(write_fixture(out,item,image,win))
    for provider in ['high','low']:
        for tag in ['L28','L29']:
            item=next(r for r in inventory if r['id']==tag and r['provider']==provider)
            x,y=item['point'];n=item['window_size'];rows.append(write_fixture(out,{**item,'id':tag+'_detail'},images[item['source']],[x-n//2,y-n//2,n,n]))
    item=next(r for r in inventory if r['id']=='L28' and r['provider']=='high')
    x,y=item['point'];rows.append(write_fixture(out,{**item,'id':'L28_rectangle'},images[item['source']],[x-512,y-384,1024,768]))
    manifest={'schema':1,'note':'No human ground truth. Native grid; identical simulated prompts across backends; boxes from prior AI trial masks, not verified reference boundaries.','items':rows,'images':list(images.values())}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8');print('fixtures',len(rows),flush=True)

def write_fixture(out,item,image,win):
    rgb,valid=read_rgb(image,win);x,y=item['point'];n=win[2]
    positives=[[x-win[0],y-win[1]]]+[[a-win[0],b-win[1]] for a,b in item.get('extra_positive_global',[])]
    negatives=[[a-win[0],b-win[1]] for a,b in item.get('negative_global',[])] or [[int(n*.12),int(win[3]*.12)],[int(n*.88),int(win[3]*.12)],[int(n*.12),int(win[3]*.88)],[int(n*.88),int(win[3]*.88)]]
    negatives=[p for p in negatives if 0<=p[0]<win[2] and 0<=p[1]<win[3] and valid[p[1],p[0]]]
    bbox=[max(0,positives[0][0]-64),max(0,positives[0][1]-64),min(win[2],positives[0][0]+64),min(win[3],positives[0][1]+64)]
    old=ROOT/'experiments/lake_review'/item['provider']/(item['id'].split('_')[0]+'.npz')
    old_item=next((r for r in json.loads((ROOT/'experiments/lake_review/inventory.json').read_text()) if r['id']==item['id'].split('_')[0] and r['provider']==item['provider']),None)
    if old.exists() and old_item:
        with np.load(old) as z:mask=z['refined'];yy,xx=np.where(mask)
        if len(xx):
            ox=old_item['point'][0]-old_item['window_size']//2-win[0];oy=old_item['point'][1]-old_item['window_size']//2-win[1]
            bbox=[max(0,int(xx.min())+ox-4),max(0,int(yy.min())+oy-4),min(win[2],int(xx.max())+ox+5),min(win[3],int(yy.max())+oy+5)]
    name=item['provider']+'_'+item['id'];file=out/(name+'.npz')
    np.savez_compressed(file,rgb=rgb,valid=valid,positives=np.array(positives,np.float32),negatives=np.array(negatives,np.float32).reshape(-1,2),box=np.array(bbox,np.float32))
    return {**item,'key':name,'window':win,'fixture':file.name,'sha256':hashlib.file_digest(file.open('rb'),'sha256').hexdigest(),'transform':image['transform'],'crs':image['crs'],'valid_pixels':int(valid.sum())}

if __name__=='__main__':main()
