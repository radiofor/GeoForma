"""Keep this Conda environment's native GIS libraries isolated on Windows.

Installed only into GeoForma through install_runtime.py. Settings affect the
current Python process and its children, never the registry or other environments.
All paths are computed from sys.prefix so the project has no machine path binding.
"""

import os
import sys
from pathlib import Path

_dll_handles = []


def configure():
    if sys.platform != "win32" or _dll_handles:
        return
    prefix = Path(getattr(sys, '_MEIPASS', sys.prefix)).resolve()
    native = prefix / "Library" / "bin"
    if not native.is_dir() and not getattr(sys,'_MEIPASS',None) and sys.prefix!=sys.base_prefix:
        base=Path(sys.base_prefix).resolve()
        if (base/'Library'/'bin').is_dir():prefix=base;native=base/'Library'/'bin'
    if not native.is_dir():
        return
    preferred = [prefix, native, prefix / "Scripts"]
    remaining = []
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry:
            continue
        try:
            candidate = Path(entry.strip('"')).resolve()
            sibling_environment = (candidate.is_relative_to(prefix.parent)
                                   and not candidate.is_relative_to(prefix))
            external_osgeo = (candidate.name.lower() == "osgeo"
                              and not candidate.is_relative_to(prefix))
            if candidate in preferred or sibling_environment or external_osgeo:
                continue
        except (OSError, ValueError):
            pass
        remaining.append(entry)
    os.environ["PATH"] = os.pathsep.join([*(str(p) for p in preferred), *remaining])
    _dll_handles.append(os.add_dll_directory(str(native)))
    for key, relative in (("GDAL_DATA", "Library/share/gdal"),
                          ("PROJ_DATA", "Library/share/proj"),
                          ("PROJ_LIB", "Library/share/proj")):
        location = prefix / relative
        if location.is_dir():
            os.environ[key] = str(location)
