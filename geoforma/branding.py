"""Project-local application artwork, shared by the entry point and window."""
from pathlib import Path
from PySide6.QtGui import QIcon


def application_icon():
    return QIcon(str(Path(__file__).resolve().parents[1] / 'assets' / 'geoforma_map_pen.ico'))
