"""Complete native fresh-process checks and high-resolution TIFF trials."""
import json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'experiments/sam_versions'

def run(name,command,timeout=1800):
    print('start',name,flush=True);started=time.perf_counter()
    with (OUT/(name+'.log')).open('w',encoding='utf-8') as f:
        p=subprocess.run(command,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,timeout=timeout)
    row={'task':name,'returncode':p.returncode,'seconds':time.perf_counter()-started}
    print('done',json.dumps(row),flush=True);return row

def main():
    status=[];manifest=json.loads((OUT/'manifest.json').read_text())
    for spec in manifest['models']:
        base=OUT/'windows'/spec['id']
        for device in ['cuda','cpu']:
            path=base/device/'results.json'
            if not path.exists() or not json.loads(path.read_text()).get('ok'):
                args=['--model',spec['id'],'--device',device]
                if device=='cpu':args+=['--keys','high_L28_detail']
                status.append(run(spec['id']+'_repair_'+device,[sys.executable,str(ROOT/'tools/evaluate_sam_versions.py'),*args]))
        status.append(run(spec['id']+'_restore',[sys.executable,str(ROOT/'tools/evaluate_sam_versions.py'),'--model',spec['id'],'--restore']))
        (OUT/'extended_status.json').write_text(json.dumps(status,indent=2))
    for spec in manifest['models']:
        path=OUT/'windows'/spec['id']/'full_high_grid8/results.json'
        if path.exists() and json.loads(path.read_text()).get('ok'):continue
        status.append(run(spec['id']+'_full_high',[sys.executable,str(ROOT/'tools/evaluate_sam_versions.py'),'--model',spec['id'],'--full','high'],timeout=1800))
        (OUT/'extended_status.json').write_text(json.dumps(status,indent=2))

if __name__=='__main__':main()
