"""Explicit re-encoding windows; never concatenate features from neighboring tiles."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from build_sam_fixtures import write_fixture
base=ROOT/'experiments/sam_versions';out=base/'expanded_fixtures';out.mkdir(parents=True,exist_ok=True)
manifest=json.loads((base/'fixtures/manifest.json').read_text());inventory=json.loads((ROOT/'experiments/lake_review/inventory.json').read_text());rows=[]
for tag,size in [('L01',4096),('L28',2048)]:
    item=next(r for r in inventory if r['id']==tag and r['provider']=='high');image=next(r for r in manifest['images'] if 'Bing-RGB' in r['path']);x,y=item['point']
    rows.append(write_fixture(out,{**item,'id':tag+'_expand'+str(size)},image,[x-size//2,y-size//2,size,size]))
(out/'manifest.json').write_text(json.dumps({**manifest,'items':rows,'note':'Expanded native raster windows re-encoded independently. SAM downsamples to its fixed input; small-target detail can change.'},indent=2),encoding='utf-8')
print('expanded fixtures ready',flush=True)
