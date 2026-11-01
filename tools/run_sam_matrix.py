"""Sequential GPU jobs with isolated processes and durable per-model evidence."""
import json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'experiments/sam_versions'

def main():
    manifest=json.loads((OUT/'manifest.json').read_text());status=[]
    for row in manifest['models']:
        if row.get('status')!='downloaded':continue
        commands=[['--model',row['id']],['--model',row['id'],'--device','cpu','--keys','high_L28_detail'],['--model',row['id'],'--full','low']]
        for index,args in enumerate(commands):
            directory=OUT/'windows'/row['id']/(['cuda','cpu','full_low_grid8'][index])
            if (directory/'results.json').exists() and json.loads((directory/'results.json').read_text()).get('ok'):continue
            start=time.perf_counter();log=OUT/(row['id']+'_'+str(index)+'.log');print('start',row['id'],index,flush=True)
            with log.open('w',encoding='utf-8') as f:
                p=subprocess.run([sys.executable,str(ROOT/'tools/evaluate_sam_versions.py'),*args],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,timeout=1200)
            status.append({'model':row['id'],'args':args,'returncode':p.returncode,'seconds':time.perf_counter()-start,'log':str(log)})
            (OUT/'matrix_status.json').write_text(json.dumps(status,indent=2),encoding='utf-8');print('done',row['id'],index,p.returncode,round(time.perf_counter()-start,1),flush=True)

if __name__=='__main__':main()
