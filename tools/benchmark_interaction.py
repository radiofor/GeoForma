"""Measure production IPC, cached decoding and drag previews on real source TIFFs."""
import copy,json,os,sys,time,threading,statistics
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from geoforma.services import ModelService
from geoforma.domain import prompt_window

def main():
    project=json.loads((ROOT/'experiments/e2e_vectors/acceptance.geoforma.json').read_text(encoding='utf-8'))
    task=SimpleNamespace(check=lambda:None,cancel_event=threading.Event(),signals=SimpleNamespace(progress=SimpleNamespace(emit=lambda *a:None)))
    service=ModelService();results=[]
    try:
        for family,variant,file in [('sam','vit_b','sam_vit_b_01ec64.pth'),('sam2.1','small','sam2.1_hiera_small.pt')]:
            config={'backend':family,'variant':variant,'device':'cuda','execution':'native','checkpoint':str(Path(os.environ['GEOFORMA_DATA_DIR'])/'models'/file)}
            for image in project['images'][:2]:
                box=[min(400,image['width']-150),400,min(600,image['width']-10),600]
                window=prompt_window([],box);request={'points':[],'box':box,'window':window}
                start=time.perf_counter();first=service.predict(image,copy.deepcopy(config),request,task);cold=time.perf_counter()-start
                elapsed=[];previews=[]
                for i in range(5):
                    request['box']=[box[0],box[1],box[2]+i,box[3]+i]
                    start=time.perf_counter();answer=service.preview(image,copy.deepcopy(config),request,task);previews.append(time.perf_counter()-start)
                    assert answer is not None and answer['mask'].shape==(256,256)
                    start=time.perf_counter();result=service.predict(image,copy.deepcopy(config),request,task);elapsed.append(time.perf_counter()-start)
                    assert result['cache_hit'] and len(result['choices'])<=1
                row={'backend':family,'variant':variant,'image':image['path'],'device':result['device'],'first_seconds':cold,'first_cache_hit':first['cache_hit'],'apply_median_seconds':statistics.median(elapsed),'preview_median_seconds':statistics.median(previews),'preview_max_seconds':max(previews)}
                results.append(row);print(json.dumps(row),flush=True)
    finally:service.close()
    (ROOT/'experiments/interaction_performance.json').write_text(json.dumps(results,indent=2),encoding='utf-8')

if __name__=='__main__':
    from multiprocessing import freeze_support
    freeze_support();main()
