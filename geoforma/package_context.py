"""Windows package identity and the signed-in-package Store build profile."""
from functools import lru_cache
import sys


@lru_cache(maxsize=1)
def current_package_family():
    if sys.platform!='win32':return None
    import ctypes
    api=ctypes.WinDLL('kernel32',use_last_error=True);size=ctypes.c_uint32()
    function=api.GetCurrentPackageFamilyName
    function.argtypes=[ctypes.POINTER(ctypes.c_uint32),ctypes.c_wchar_p];function.restype=ctypes.c_long
    result=function(ctypes.byref(size),None)
    if result==15700:return None  # APPMODEL_ERROR_NO_PACKAGE
    if result!=122:raise OSError(result,'无法读取 Windows 包身份。')
    buffer=ctypes.create_unicode_buffer(size.value)
    result=function(ctypes.byref(size),buffer)
    if result:raise OSError(result,'无法读取 Windows 包身份。')
    return buffer.value


@lru_cache(maxsize=1)
def is_store_build():
    from .distribution import resource_root
    from .atomic_io import read_json
    path=resource_root()/'geoforma/store-profile.json'
    if not path.is_file():return False
    profile=read_json(path)
    if profile.get('kind')!='geoforma-store-profile-v1':raise ValueError('商店运行配置无效。')
    return True


def configure_application_id(setter=None):
    # Packaged processes already have the AUMID assigned by their manifest.
    if sys.platform!='win32' or current_package_family():return
    if setter is None:
        import ctypes
        setter=ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
    setter('GeoForma.Desktop')
