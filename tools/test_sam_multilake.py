"""Inspectable multi-point editing of AMG candidates, without human ground truth."""
import argparse,json,sys,time
from pathlib import Path
import numpy as np,torch
from evaluate_sam_versions import load,best,stats,overlay,OUT,FIX

def worker(name):
    spec=next(r for r in json.loads((OUT/'manifest.json').read_text())['models'] if r['id']==name);base=OUT/'windows'/name/'multilake';base.mkdir(parents=True,exist_ok=True)
    model,p,Generator=load(spec,'cuda');g=Generator(model,points_per_side=32,points_per_batch=16,pred_iou_thresh=.88 if spec['generation']=='sam1' else .8,stability_score_thresh=.95,crop_n_layers=0,min_mask_region_area=0);rows=[]
    for key in ['high_L28_detail','high_L29_detail']:
        with np.load(FIX/(key+'.npz')) as z:rgb=z['rgb'];valid=z['valid'];first=z['positives'];negative=z['negatives']
        extra=np.array([[281,279],[300,291]] if 'L28' in key else [[261,234],[253,276]],np.float32)
        extra_negative=np.array([[310,275],[252,298]] if 'L28' in key else [[279,265],[231,260]],np.float32)
        points=np.concatenate([first,extra,negative,extra_negative]);labels=np.array([1]*(len(first)+2)+[0]*(len(negative)+2));box=np.array([235,237,315,309] if 'L28' in key else [234,220,278,291],np.float32)
        with torch.inference_mode():
            candidates=g.generate(rgb);hits=[r for r in candidates if r['segmentation'][256,256]];p.set_image(rgb)
            selected=min(hits,key=lambda c:c['area']) if hits else None;seed=selected['segmentation']&valid if selected else np.zeros(valid.shape,bool);prior=None
            if selected:prior=torch.nn.functional.interpolate(torch.from_numpy(np.where(seed,4.,-4.).astype(np.float32))[None,None],size=(256,256),mode='bilinear',align_corners=False)[0].numpy()
            initial,_,_=best(p,valid,np.concatenate([first,negative]),np.array([1]*len(first)+[0]*len(negative)),prior=prior)
            corrected,_,_=best(p,valid,points,labels,prior=prior);fresh,_,_=best(p,valid,points,labels);boxed,_,_=best(p,valid,points,labels,box=box)
            undo,_,_=best(p,valid,np.concatenate([first,negative]),np.array([1]*len(first)+[0]*len(negative)),prior=prior);assert np.array_equal(undo,initial)
        row={'fixture':key,'candidate_count':len(candidates),'point_hits':len(hits),'seed_pixels':int(seed.sum()),'initial':stats(initial,first,negative),'multi_seed':stats(corrected,points[:len(first)+2],points[len(first)+2:]),'multi_fresh':stats(fresh,points[:len(first)+2],points[len(first)+2:]),'multi_box':stats(boxed,points[:len(first)+2],points[len(first)+2:]),'undo_reapply_exact':True,'points_local':points.tolist(),'labels':labels.tolist(),'box_local':box.tolist(),'note':'Additional points selected by visual inspection of RGB, not human-verified reference labels. Binary seed is a heuristic prior, not original AMG logits.'}
        np.savez_compressed(base/(key+'.npz'),seed=seed,initial=initial,multi_seed=corrected,multi_fresh=fresh,multi_box=boxed)
        for tag,mask in [('seed',seed),('initial',initial),('multi_seed',corrected),('multi_fresh',fresh),('multi_box',boxed)]:overlay(rgb,mask,points,labels).save(base/(key+'_'+tag+'.png'))
        rows.append(row);print(name,key,row['seed_pixels'],'->',row['multi_seed']['pixels'],row['multi_fresh']['pixels'],row['multi_box']['pixels'],flush=True)
    (base/'results.json').write_text(json.dumps({'ok':True,'model':name,'trials':rows},indent=2),encoding='utf-8')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--model');args=parser.parse_args()
    if args.model:worker(args.model);return
    import subprocess
    started=time.monotonic()
    while not (OUT/'evaluation_complete.json').exists():
        if time.monotonic()-started>3600:raise TimeoutError('Waiting for prior GPU tests')
        time.sleep(2)
    status=[]
    for model in json.loads((OUT/'manifest.json').read_text())['models']:
        name=model['id'];print('start multilake',name,flush=True)
        with (OUT/(name+'_multilake.log')).open('w',encoding='utf-8') as f:r=subprocess.run([sys.executable,__file__,'--model',name],stdout=f,stderr=subprocess.STDOUT,timeout=180)
        status.append({'model':name,'returncode':r.returncode});(OUT/'multilake_status.json').write_text(json.dumps(status,indent=2),encoding='utf-8');print('done multilake',name,r.returncode,flush=True)

if __name__=='__main__':main()
