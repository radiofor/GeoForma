"""Paths shared by source runs, frozen builds and optional offline payloads."""
import sys
from pathlib import Path

VERSION='1.0.5'

def resource_root():return Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))
def install_root():return Path(sys.executable).parent if getattr(sys,'frozen',False) else resource_root()

def bundled_checkpoint(name):
    for root in [install_root(),resource_root()]:
        path=root/'models'/name
        if path.is_file():return path
    return None

