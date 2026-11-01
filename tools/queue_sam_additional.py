"""Wait for the sequential full-image matrix to release its GPU, then run follow-ups."""
import json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'experiments/sam_versions'
started=time.monotonic()
while True:
    try:rows=json.loads((OUT/'extended_status.json').read_text())
    except (OSError,ValueError):rows=[]
    if any(r['task']=='sam2.1_large_full_high' for r in rows):break
    if time.monotonic()-started>10800:raise TimeoutError('Full-image matrix did not complete')
    time.sleep(2)
for script in ['run_sam_additional.py','summarize_sam_versions.py','create_sam_report.py']:
    result=subprocess.run([sys.executable,str(ROOT/'tools'/script)],cwd=ROOT)
    if result.returncode:raise RuntimeError(script+' failed')
summary=json.loads((OUT/'summary.json').read_text());additional=json.loads((OUT/'additional_status.json').read_text())
passed=len(summary)==11 and all(r.get('cpu_ok') and r.get('fresh_process_restore') and r.get('high_full_ok') and r.get('low_full_ok') for r in summary) and all(r['returncode']==0 for r in additional)
(OUT/'evaluation_complete.json').write_text(json.dumps({'ok':passed,'completed_at':time.strftime('%Y-%m-%d %H:%M:%S'),'note':'Detailed individual results determine pass/fail; model scores are not ground-truth accuracy.'},indent=2),encoding='utf-8')
