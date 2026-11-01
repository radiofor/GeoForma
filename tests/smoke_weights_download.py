"""Resume the final official ViT-B bytes, verify hash, then load the real model."""
import sys,os,json,threading,time,argparse
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from main import configure_runtime
configure_runtime()
from PIL import Image
from geoforma.weights import default_checkpoint,SPECS,BASE
from geoforma.services import ModelService
from geoforma.model_catalog import MODELS


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--model',default='sam1_vit_b');args=parser.parse_args()
    spec=next(s for s in MODELS if s['id']==args.model)
    records=json.loads((ROOT/'experiments/sam_versions/manifest.json').read_text())['models']
    original=Path(next(s['path'] for s in records if s['id']==args.model));size=original.stat().st_size
    root=ROOT/'experiments/weights_download'/args.model;os.environ['GEOFORMA_DATA_DIR']=str(root)
    target=default_checkpoint(spec['variant'],spec['backend']);target.parent.mkdir(parents=True,exist_ok=True);part=target.with_suffix(target.suffix+'.part')
    assert target.resolve().is_relative_to(root.resolve()) and target.resolve()!=original.resolve()
    target.unlink(missing_ok=True)
    remaining=size-65536
    with original.open('rb') as source,part.open('wb') as dst:
        while remaining:
            block=source.read(min(1048576,remaining));dst.write(block);remaining-=len(block)
    part.with_suffix(part.suffix+'.json').write_text(json.dumps({'url':spec['url'],'total':size}),encoding='utf-8')
    class Task:
        cancel_event=threading.Event()
        signals=SimpleNamespace(progress=SimpleNamespace(emit=lambda a,b,message:print(message,flush=True)))
        def check(self):
            if self.cancel_event.is_set():raise RuntimeError('Cancelled')
    service=ModelService();start=time.monotonic()
    try:
        result=service.prepare_model({'backend':spec['backend'],'variant':spec['variant'],'device':'cuda','checkpoint':str(root/'missing.pth')},Task())
        assert Path(result['checkpoint'])==target and target.stat().st_size==size
        manifest=json.loads(target.with_suffix('.download.json').read_text());assert manifest['sha256']==spec['sha256']
        result.update(official_resume=True,sha256_verified=True,bytes=size,elapsed=round(time.monotonic()-start,2))
        (root/'results.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2),flush=True)
    finally:
        service.close()
        # Only the duplicate test model is removed; the user's real model stays intact.
        if target.exists():target.unlink()


if __name__=='__main__':
    from multiprocessing import freeze_support
    freeze_support();main()
