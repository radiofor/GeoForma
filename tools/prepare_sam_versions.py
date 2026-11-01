"""Fetch pinned official sources and public checkpoints for an isolated evaluation."""
import concurrent.futures, hashlib, json, os, re, time, urllib.request, zipfile,importlib.metadata
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'experiments'/'sam_versions'
SOURCES=ROOT/'environment'/'sam_sources'
MODELS=Path(os.environ['LOCALAPPDATA'])/'GeoForma'/'models'

def fetch(url,path):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():return
    part=path.with_name(path.name+'.part')
    for attempt in range(4):
        offset=part.stat().st_size if part.exists() else 0
        req=urllib.request.Request(url,headers={'User-Agent':'GeoForma-eval','Range':f'bytes={offset}-'} if offset else {'User-Agent':'GeoForma-eval'})
        try:
            with urllib.request.urlopen(req,timeout=45) as response:
                resumed=response.status==206
                total=int(response.headers.get('Content-Length',0))+(offset if resumed else 0)
                done=offset if resumed else 0;last=time.monotonic()
                with part.open('ab' if resumed else 'wb') as f:
                    while block:=response.read(4*1024*1024):
                        f.write(block);done+=len(block)
                        if time.monotonic()-last>15:
                            print(path.name,done//1048576,'/',total//1048576,'MiB',flush=True);last=time.monotonic()
                if total and done!=total:raise IOError('Incomplete response')
            os.replace(part,path);print('ready',path.name,path.stat().st_size,flush=True);return
        except Exception as e:
            print('retry',path.name,type(e).__name__,str(e),flush=True)
            if attempt==3:raise
            time.sleep(2)

def main():
    OUT.mkdir(parents=True,exist_ok=True);SOURCES.mkdir(parents=True,exist_ok=True)
    distribution=importlib.metadata.distribution('segment-anything')
    direct=json.loads(distribution.read_text('direct_url.json') or '{}')
    manifest={'sources':{'sam1':{'package_version':distribution.version,'direct_url':direct}},'models':[],'deferred':['sam3','sam3.1']}
    for repo in ['sam2','sam3']:
        with urllib.request.urlopen(f'https://api.github.com/repos/facebookresearch/{repo}/commits/main',timeout=30) as r:commit=json.load(r)['sha']
        archive=SOURCES/(repo+'_'+commit+'.zip');fetch(f'https://codeload.github.com/facebookresearch/{repo}/zip/{commit}',archive)
        target=SOURCES/(repo+'-'+commit)
        if not target.exists():
            with zipfile.ZipFile(archive) as z:z.extractall(SOURCES)
        manifest['sources'][repo]={'commit':commit,'path':str(target),'url':f'https://github.com/facebookresearch/{repo}/tree/{commit}'}
    urls=[]
    for variant,name in [('vit_b','sam_vit_b_01ec64.pth'),('vit_l','sam_vit_l_0b3195.pth'),('vit_h','sam_vit_h_4b8939.pth')]:
        urls.append(('sam1_'+variant,'sam1',variant,'https://dl.fbaipublicfiles.com/segment_anything/'+name))
    readme=(Path(manifest['sources']['sam2']['path'])/'README.md').read_text(encoding='utf-8')
    for generation,date in [('sam2','072824'),('sam2.1','092824')]:
        for variant in ['tiny','small','base_plus','large']:
            name=f'{generation}_hiera_{variant}.pt';url=f'https://dl.fbaipublicfiles.com/segment_anything_2/{date}/{name}'
            assert url in readme
            urls.append((generation+'_'+variant,generation,variant,url))
    for name,generation,variant,url in urls:
        manifest['models'].append({'id':name,'generation':generation,'variant':variant,'url':url,'path':str(MODELS/url.rsplit('/',1)[1])})
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures={pool.submit(fetch,r['url'],Path(r['path'])):r for r in manifest['models']}
        for f in concurrent.futures.as_completed(futures):
            r=futures[f]
            try:
                f.result();p=Path(r['path']);r.update(bytes=p.stat().st_size,sha256=hashlib.file_digest(p.open('rb'),'sha256').hexdigest(),status='downloaded')
            except Exception as e:r.update(status='download_failed',error=str(e))
            (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print('complete',flush=True)

if __name__=='__main__':main()
