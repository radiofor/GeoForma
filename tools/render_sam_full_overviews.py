"""Display-only union of detail candidates; no semantic filtering or training labels."""
import json,sys
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from geoforma.raster import read_rgb
OUT=ROOT/'experiments/sam_versions';manifest=json.loads((OUT/'fixtures/manifest.json').read_text());models=json.loads((OUT/'manifest.json').read_text())['models']
for provider in ['low','high']:
    image=next(r for r in manifest['images'] if ('Bing-RGB' in r['path'])==(provider=='high'));rgb,valid=read_rgb(image,[0,0,image['width'],image['height']],max_size=1024);scale=rgb.shape[1]/image['width']
    for model in models:
        base=OUT/'windows'/model['id']/('full_'+provider+'_grid8');file=base/'results.json'
        if not file.exists():continue
        report=json.loads(file.read_text())
        if not report.get('ok'):continue
        union=Image.new('L',(rgb.shape[1],rgb.shape[0]));count=0
        for row in report['tiles']:
            data=base/(str(row['tile'])+'.npz')
            if not data.exists():continue
            with np.load(data) as z:masks=np.unpackbits(z['masks'],axis=-1,count=int(z['shape'][1])).astype(bool)
            areas=masks.sum(axis=(1,2));detail=masks[areas<=masks.shape[1]*masks.shape[2]*.08]
            if not len(detail):continue
            count+=len(detail);mask=np.any(detail,axis=0);win=row['window'];layer=Image.fromarray(mask.astype(np.uint8)*255).resize((max(1,round(win[2]*scale)),max(1,round(win[3]*scale))),Image.Resampling.NEAREST)
            # Lighten keeps accumulated overlapping tile coverage; display does not claim deduplication.
            temp=Image.new('L',union.size);temp.paste(layer,(round(win[0]*scale),round(win[1]*scale)))
            from PIL import ImageChops
            union=ImageChops.lighter(union,temp)
        selected=np.asarray(union)>0;composite=rgb.copy();composite[selected]=(composite[selected]*.45+np.array([255,140,0])*.55).astype(np.uint8)
        result=Image.new('RGB',(rgb.shape[1]*2,rgb.shape[0]+32),(20,28,36));result.paste(Image.fromarray(rgb),(0,32));result.paste(Image.fromarray(composite),(rgb.shape[1],32));draw=ImageDraw.Draw(result);draw.text((8,8),model['id']+' '+provider+' RGB',fill='white');draw.text((rgb.shape[1]+8,8),'DETAIL CANDIDATE UNION - NOT LAKE LABELS: '+str(count),fill='white');result.save(base/'detail_overview.png');print(model['id'],provider,'overview',flush=True)
