"""Exercise the real optional-resource installer in an isolated QA data root."""
import argparse,json,os,sys,threading,time
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

class Task:
    def __init__(self):
        self.cancel_event=threading.Event();self.last=0
        self.signals=SimpleNamespace(progress=SimpleNamespace(emit=self.report))
    def check(self):
        from geoforma.tasks import Cancelled
        if self.cancel_event.is_set():raise Cancelled()
    def report(self,current,total,text):
        now=time.monotonic()
        if now-self.last>3 or current==total and total:self.last=now;print(current,total,text,flush=True)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--profile',choices=['cpu','cu126'],default='cpu');parser.add_argument('--data',type=Path,required=True);args=parser.parse_args()
    os.environ['GEOFORMA_DATA_DIR']=str(args.data.resolve())
    from main import configure_runtime
    configure_runtime()
    from geoforma.native_runtime import NativeRuntimeManager,profile,runtime_root
    from geoforma.atomic_io import atomic_json
    manager=NativeRuntimeManager();state=manager.install(args.profile,Task())
    sources=[runtime_root()/'downloads'/wheel['filename'] for wheel in profile(args.profile)['wheels']]
    manual=manager.install(args.profile,Task(),sources)
    assert state['generation']==manual['generation']
    atomic_json(args.data.parent/('runtime_'+args.profile+'_report.json'),dict(ok=True,automatic=state,manual=manual),indent=2)
    print('AUTOMATIC + LOCAL IMPORT PASSED',flush=True)

if __name__=='__main__':
    import multiprocessing
    multiprocessing.freeze_support();main()
