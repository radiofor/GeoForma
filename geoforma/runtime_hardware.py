"""Read the NVIDIA driver inventory during background startup, without Torch."""
import os,subprocess,sys,threading
from pathlib import Path


def detect_hardware():
    if sys.platform!='win32':return {}
    locations=[Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/nvidia-smi.exe',
        Path(os.environ.get('ProgramFiles','C:/Program Files'))/'NVIDIA Corporation/NVSMI/nvidia-smi.exe']
    program=next((path for path in locations if path.is_file()),None)
    if program is None:return {}
    try:
        result=subprocess.run([str(program),'--query-gpu=name','--format=csv,noheader'],capture_output=True,
            timeout=2,creationflags=subprocess.CREATE_NO_WINDOW,encoding='utf-8',errors='replace',check=True)
        names=[line.strip() for line in result.stdout.splitlines() if line.strip()]
        return {'nvidia':names} if names else {}
    except (OSError,subprocess.SubprocessError):return {}


class HardwareProbe:
    """Overlap driver discovery with startup imports without touching Qt."""
    def __init__(self):
        self._done=threading.Event();self._value=None;self._error=None
        def run():
            try:self._value=detect_hardware()
            except Exception as error:self._error=error
            finally:self._done.set()
        threading.Thread(target=run,name='geoforma-hardware-probe',daemon=True).start()

    def result(self,check):
        while not self._done.wait(.05):check()
        check()
        if self._error is not None:raise self._error
        return self._value


def recommended_profile(model,hardware,installed=None):
    if model.get('device')=='cpu':return 'cpu'
    if hardware.get('nvidia'):return 'cu126'
    return installed['profile'] if installed else 'cpu'
