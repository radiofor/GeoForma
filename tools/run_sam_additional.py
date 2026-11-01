"""Dense small-target sensitivity and expanded-window tests after the GPU matrix."""
import json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'experiments/sam_versions'
rows=[]
for model in json.loads((OUT/'manifest.json').read_text())['models']:
    for flag in ['--dense','--expanded']:
        name=model['id']+'_'+flag[2:];print('start',name,flush=True)
        with (OUT/(name+'.log')).open('w',encoding='utf-8') as f:
            p=subprocess.run([sys.executable,str(ROOT/'tools/evaluate_sam_versions.py'),'--model',model['id'],flag],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,timeout=600)
        rows.append({'task':name,'returncode':p.returncode});(OUT/'additional_status.json').write_text(json.dumps(rows,indent=2),encoding='utf-8');print('done',name,p.returncode,flush=True)
for name in ['sam2.1_small','sam2.1_large']:
    for restore in [False,True]:
        task=name+'_bf16'+('_restore' if restore else '')
        args=['--model',name,'--precision','bfloat16']+(['--restore'] if restore else [])
        with (OUT/(task+'.log')).open('w',encoding='utf-8') as f:p=subprocess.run([sys.executable,str(ROOT/'tools/evaluate_sam_versions.py'),*args],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,timeout=300)
        rows.append({'task':task,'returncode':p.returncode});(OUT/'additional_status.json').write_text(json.dumps(rows,indent=2),encoding='utf-8');print('done',task,p.returncode,flush=True)
