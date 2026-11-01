"""Run this file with the GeoForma interpreter to open Qt Designer."""

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QLibraryInfo

def designer_command():
    designer = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.BinariesPath)) / "designer.exe"
    plugins = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath))
    if not designer.is_file() or not (plugins / "platforms" / "qwindows.dll").is_file():
        raise RuntimeError("Qt Designer or its Windows platform plugin is missing.")
    env = os.environ.copy()
    env["QT_PLUGIN_PATH"] = str(plugins)
    env["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(plugins / "platforms")
    env["QT_QPA_PLATFORM"] = "windows"
    env["PATH"] = os.pathsep.join([str(Path(sys.prefix) / "Library" / "bin"), env.get("PATH", "")])
    return [str(designer)], env


if __name__ == "__main__":
    command, environment = designer_command()
    raise SystemExit(subprocess.call([*command, *sys.argv[1:]], env=environment))
