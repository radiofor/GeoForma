"""Fetch only small, pinned companion wheels for inclusion in the installer."""
import sys,threading
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

def main():
    from main import configure_runtime
    configure_runtime()
    from geoforma.native_runtime import catalog
    from geoforma.resource_files import acquire
    task=SimpleNamespace(cancel_event=threading.Event(),check=lambda:None,
        signals=SimpleNamespace(progress=SimpleNamespace(emit=lambda *args:None)))
    for profile in catalog()['profiles'].values():
        for wheel in profile['wheels']:
            if wheel['name']=='torchvision':print(acquire(wheel,ROOT/'environment/resource-wheels',task),flush=True)

if __name__=='__main__':main()
