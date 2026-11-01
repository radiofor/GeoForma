"""Save separate Conda and pip locks; do not reinstall Conda GIS wheels via pip."""

import importlib.metadata as metadata
import json
import subprocess
import sys
from pathlib import Path

folder = Path(__file__).resolve().parent
prefix = Path(sys.prefix)
conda_python = prefix.parent.parent / "python.exe"
command = [str(conda_python), "-m", "conda", "list", "--prefix", str(prefix)]
explicit = subprocess.run(command + ["--explicit"], check=True, capture_output=True,
                          text=True, encoding="utf-8").stdout
(folder / "conda-win-64.lock.txt").write_text(explicit, encoding="utf-8")
records = json.loads(subprocess.run(command + ["--json"], check=True,
                                  capture_output=True, text=True, encoding="utf-8").stdout)
(folder / "installed-packages.json").write_text(
    json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
torch_report = json.loads((folder / "torch-install.json").read_text(encoding="utf-8-sig"))
torch_urls = {p["metadata"]["name"].lower(): p["download_info"]
              for p in torch_report["install"]
              if p["metadata"]["name"].lower() in ("torch", "torchvision")}
lines = ["# Windows x64 / Python 3.13. Install conda-win-64.lock.txt first.",
         "--index-url https://pypi.org/simple"]
for record in sorted(records, key=lambda p: p["name"].lower()):
    if record.get("channel") != "pypi":
        continue
    name = record["name"]
    distribution = metadata.distribution(name)
    direct_url = distribution.read_text("direct_url.json")
    if name.lower() in torch_urls:
        info = torch_urls[name.lower()]
        sha256 = info.get("archive_info", {}).get("hashes", {}).get("sha256")
        suffix = f"#sha256={sha256}" if sha256 else ""
        lines.append(f"{name} @ {info['url']}{suffix}")
    elif name.lower()=='sam-2':
        sys.path.insert(0,str(folder.parent))
        from geoforma.model_catalog import SAM2_COMMIT
        import hashlib
        archive=folder/'sam_sources'/('sam2_'+SAM2_COMMIT+'.zip')
        with archive.open('rb') as stream:checksum=hashlib.file_digest(stream,'sha256').hexdigest()
        lines.append(f'SAM-2 @ https://github.com/facebookresearch/sam2/archive/{SAM2_COMMIT}.zip#sha256={checksum}')
    elif direct_url:
        info = json.loads(direct_url)
        sha256 = info.get("archive_info", {}).get("hashes", {}).get("sha256")
        suffix = f"#sha256={sha256}" if sha256 else ""
        lines.append(f"{name} @ {info['url']}{suffix}")
    else:
        lines.append(f"{name}=={distribution.version}")
(folder / "requirements-win-pip.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
versions = {name: metadata.version(name) for name in
            ("PySide6", "torch", "torchvision", "numpy", "rasterio", "GDAL",
             "shapely", "pytest", "pyinstaller", "segment-anything")}
print(json.dumps({"python": sys.version, "versions": versions,
                  "pip_package_count": len(lines) - 2}, ensure_ascii=False, indent=2))
