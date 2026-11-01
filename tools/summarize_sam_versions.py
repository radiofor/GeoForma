"""Aggregate measured evidence and create reproducible visual comparison sheets."""
import csv,json,statistics
from pathlib import Path
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'experiments/sam_versions'

def main():
    manifest=json.loads((OUT/'manifest.json').read_text());rows=[];models=[]
    for spec in manifest['models']:
        base=OUT/'windows'/spec['id'];file=base/'cuda/results.json'
        if not file.exists():continue
        r=json.loads(file.read_text());trials=r['trials']
        if not r.get('ok'):continue
        models.append(spec['id']);row={'model':spec['id'],'trials':len(trials),'encode_ms':round(statistics.median(t['encode_seconds'] for t in trials)*1000,2),'point_ms':round(statistics.median(t['point_seconds'] for t in trials)*1000,2),'refine_ms':round(statistics.median(t['refine_seconds'] for t in trials)*1000,2),'gpu_mib':round(r['peak_cuda_allocated_mib'],1),'weights_mib':round(spec['bytes']/1048576,1),'positive_hit_trials':sum(t['refine']['positive_hits']>=1 for t in trials),'negative_leak_trials':sum(t['refine']['negative_leaks']>0 for t in trials),'edge_touch_trials':sum(t['refine']['touches_window'] for t in trials),'cache_exact':all(t.get('disk_restore_exact',True) for t in trials),'fresh_process_restore':(base/'cuda/fresh_process_restore.json').exists()}
        cpu=base/'cpu/results.json'
        if cpu.exists():
            c=json.loads(cpu.read_text());row['cpu_encode_ms']=round(c['trials'][0]['encode_seconds']*1000,2);row['cpu_ok']=c.get('ok',False)
        for provider in ['low','high']:
            f=base/('full_'+provider+'_grid8/results.json')
            if f.exists():
                q=json.loads(f.read_text());row[provider+'_full_ok']=q.get('ok',False);row[provider+'_full_tiles']=len(q['tiles']);row[provider+'_full_candidates']=q.get('total_candidates');row[provider+'_full_seconds']=q.get('elapsed_seconds');row[provider+'_point_hit_count']=sum(bool(v) for v in q.get('coverage',{}).values())
        rows.append(row)
    (OUT/'summary.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
    if rows:
        fields=list(dict.fromkeys(k for r in rows for k in r))
        with (OUT/'summary.csv').open('w',newline='',encoding='utf-8-sig') as f:w=csv.DictWriter(f,fields);w.writeheader();w.writerows(rows)
    keys=['high_L01','low_L01','high_L09','low_L09','high_L28_detail','high_L29_detail','low_L28','low_L28_detail','low_L29','low_L29_detail','high_L28_rectangle']
    for page in range((len(models)+3)//4):
        group=models[page*4:page*4+4];sheet=Image.new('RGB',(280*(len(group)+1),300*len(keys)),(25,30,36));d=ImageDraw.Draw(sheet)
        for i,key in enumerate(keys):
            import numpy as np
            with np.load(OUT/'fixtures'/(key+'.npz')) as z:rgb=Image.fromarray(z['rgb']).resize((280,280))
            sheet.paste(rgb,(0,i*300+20));d.text((5,i*300+3),key+' RGB',fill='white')
            for j,model in enumerate(group):
                file=OUT/'windows'/model/'cuda'/(key+'_refine.png')
                if file.exists():sheet.paste(Image.open(file),((j+1)*280,i*300+20))
                d.text(((j+1)*280+5,i*300+3),model,fill='white')
        sheet.save(OUT/('comparison_'+str(page)+'.png'))
    # Browser review uses the original saved RGB/masks and never writes labels.
    import numpy as np
    for item in json.loads((OUT/'fixtures/manifest.json').read_text())['items']:
        file=OUT/'fixtures'/(item['key']+'_rgb.png')
        if not file.exists():
            with np.load(OUT/'fixtures'/item['fixture']) as z:Image.fromarray(z['rgb']).resize((280,280)).save(file)
    parts=['<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>GeoForma SAM 对照测试</title><style>body{background:#111820;color:#e8eff5;font:16px system-ui;margin:24px}select{padding:8px;margin:8px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}.card{background:#1e2935;padding:12px;border-radius:8px}img{width:100%;image-rendering:auto}small{color:#aab9c8}</style><h1>GeoForma · SAM 对照测试</h1><p>真实预训练模型与相同输入。橙色为掩膜，绿色为正点，红色为负点。测试提示包含模拟点；没有人工真值，模型分数、像素面积和点命中率均不等于精度。候选多点补测仅包含高分辨率 L28/L29，选择该模式时会切换到对应样本。</p><label>样本<select id="sample"></select></label><label>结果<select id="mode"><option value="refine">正负点修正</option><option value="point">单正点</option><option value="box">框选</option><option value="multi_seed">候选多点修正</option><option value="multi_fresh">清除先验多点重分割</option><option value="multi_box">框＋多点</option></select></label><div class="grid" id="grid"></div><script>']
    parts.append('const models='+json.dumps(models)+';const samples='+json.dumps([r['key'] for r in json.loads((OUT/'fixtures/manifest.json').read_text())['items']])+';')
    parts.append("const sample=document.querySelector('#sample'),mode=document.querySelector('#mode');for(const k of samples){const o=document.createElement('option');o.value=k;o.textContent=k;sample.append(o)}function show(){const multi=mode.value.startsWith('multi_');if(multi&&!['high_L28_detail','high_L29_detail'].includes(sample.value))sample.value='high_L28_detail';document.querySelector('#grid').replaceChildren(...['RGB',...models].map(m=>{const card=document.createElement('div');card.className='card';const title=document.createElement('h3');title.textContent=m;const img=document.createElement('img');img.src=m==='RGB'?'fixtures/'+sample.value+'_rgb.png':'windows/'+m+'/'+(multi?'multilake':'cuda')+'/'+sample.value+'_'+mode.value+'.png';card.append(title,img);return card}))}sample.onchange=mode.onchange=show;show();</script></html>")
    (OUT/'review.html').write_text(''.join(parts),encoding='utf-8');print(json.dumps(rows,indent=2),flush=True)

if __name__=='__main__':main()
