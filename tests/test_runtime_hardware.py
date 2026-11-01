from types import SimpleNamespace
from geoforma import runtime_hardware as hardware


def test_background_nvidia_detection_is_bounded_and_does_not_import_torch(monkeypatch):
    calls=[];monkeypatch.setattr(hardware.sys,'platform','win32')
    monkeypatch.setattr(hardware.Path,'is_file',lambda path:True)
    def query(args,**kwargs):calls.append((args,kwargs));return SimpleNamespace(stdout='NVIDIA GeForce RTX 4060 Ti\n')
    monkeypatch.setattr(hardware.subprocess,'run',query)
    assert hardware.detect_hardware()=={'nvidia':['NVIDIA GeForce RTX 4060 Ti']}
    assert calls[0][1]['timeout']==2 and calls[0][1]['creationflags']==hardware.subprocess.CREATE_NO_WINDOW


def test_hardware_query_failure_keeps_installed_profile_or_cpu(monkeypatch):
    monkeypatch.setattr(hardware.sys,'platform','win32');monkeypatch.setattr(hardware.Path,'is_file',lambda path:True)
    def fail(*args,**kwargs):raise hardware.subprocess.TimeoutExpired('nvidia-smi',2)
    monkeypatch.setattr(hardware.subprocess,'run',fail)
    assert hardware.detect_hardware()=={}
    assert hardware.recommended_profile({'device':'cuda'},{})=='cpu'
    assert hardware.recommended_profile({'device':'cuda'},{},{'profile':'cu126'})=='cu126'
