"""Download official SAM assets without changing the installed environment."""

import hashlib
import json
import os
from pathlib import Path
import urllib.request

COMMIT = "dca509fe793f601edb92606367a655c15ac00fdf"


def data_root():
    return Path(os.environ.get("GEOFORMA_DATA_DIR", Path(os.environ["LOCALAPPDATA"]) / "GeoForma"))


def main():
    root = data_root()
    assets = {
        "models/sam_vit_b_01ec64.pth": "https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth",
        "samples/truck.jpg": f"https://raw.githubusercontent.com/facebookresearch/segment-anything/{COMMIT}/notebooks/images/truck.jpg",
        "models/sam_license.txt": f"https://raw.githubusercontent.com/facebookresearch/segment-anything/{COMMIT}/LICENSE",
    }
    records = []
    for relative, url in assets.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            part = target.with_suffix(target.suffix + ".part")
            print(f"Downloading {relative}", flush=True)
            with urllib.request.urlopen(url, timeout=60) as response, part.open("wb") as out:
                expected = response.headers.get("Content-Length")
                total = 0
                last = 0
                while block := response.read(1024 * 1024):
                    out.write(block)
                    total += len(block)
                    if total - last >= 50 * 1024 * 1024:
                        print(f"{total // (1024 * 1024)} MiB downloaded", flush=True)
                        last = total
            if expected is not None and total != int(expected):
                raise RuntimeError("Incomplete download; partial file retained")
            part.replace(target)
        with target.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        records.append({"path": str(target), "source": url, "bytes": target.stat().st_size,
                        "sha256": digest})
    manifest = {"backend": "meta_sam", "model_type": "vit_b", "source_commit": COMMIT,
                "hash_note": "Locally computed SHA256; not an independently published checksum.",
                "assets": records}
    (root / "model_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2), flush=True)


if __name__ == "__main__":
    main()
