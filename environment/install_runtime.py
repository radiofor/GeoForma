"""Install the documented, environment-local Windows DLL bootstrap."""

import shutil
import sys
import sysconfig
from pathlib import Path

if sys.version_info[:2] != (3, 13) or Path(sys.prefix).name.lower() != "geoforma":
    raise SystemExit("Run this installer with the GeoForma Python 3.13 interpreter")

site = Path(sysconfig.get_path("purelib"))
source = Path(__file__).with_name("_geoforma_runtime.py")
target = site / source.name
pth = site / "geoforma_runtime.pth"
pth_content = "import _geoforma_runtime; _geoforma_runtime.configure()\n"
if target.exists() and target.read_bytes() != source.read_bytes():
    raise SystemExit(f"Refusing to overwrite a different existing file: {target}")
if pth.exists() and pth.read_text(encoding="utf-8") != pth_content:
    raise SystemExit(f"Refusing to overwrite a different existing file: {pth}")
shutil.copyfile(source, target)
pth.write_text(pth_content, encoding="utf-8")
print(f"Installed environment-local runtime configuration: {pth}")
