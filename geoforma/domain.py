from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from uuid import uuid4


def uid():
    return uuid4().hex


def data_dir():
    path = Path(os.environ.get("GEOFORMA_DATA_DIR", str(Path(os.environ.get("LOCALAPPDATA", Path.home())) / "GeoForma")))
    path.mkdir(parents=True, exist_ok=True)
    return path


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def new_project(model=None):
    from .model_preferences import recommended_model,normalize_model
    from .export_settings import DEFAULT_LABEL_FIELD
    return {"schema": 1, "cache_id": uid(), "name": "Untitled", "images": [], "labels": [],
            "classes": [{"id": 1, "name": "类别 1"}], "next_class_id": 2,
            "model": normalize_model(model) if model is not None else recommended_model(),
            "workspace": {"single_polygon": True}, "export_crs": "", "export_label_field": DEFAULT_LABEL_FIELD,
            "smoothing": {"individual": {"enabled": True, "value": 1.0}}}


def tiles(bounds, width, height, core=768, halo=128):
    x, y, w, h = bounds
    x0, y0 = max(0, int(x) // core * core), max(0, int(y) // core * core)
    x1, y1 = min(width, math.ceil(x + w)), min(height, math.ceil(y + h))
    for row in range(y0, y1, core):
        for col in range(x0, x1, core):
            yield (col - halo, row - halo, core + 2 * halo, core + 2 * halo)


def prompt_window(points, box=None, current=None, expand=False):
    coords = [(p[0], p[1]) for p in points]
    if box:
        coords += [(box[0], box[1]), (box[2], box[3])]
    if not coords:
        if current:
            from .contracts import validate_window
            return validate_window(current,8192)
        raise ValueError("请先添加正点或框选目标。")
    xs, ys = zip(*coords)
    if current and not expand and max(current[2:])<=8192:
        x, y, w, h = current
        if min(xs) >= x and min(ys) >= y and max(xs) < x+w and max(ys) < y+h:
            return tuple(current)
    size = max(1024, math.ceil((max(max(xs)-min(xs), max(ys)-min(ys)) + 256) / 256) * 256)
    if expand and current:
        size = max(size, int(current[2] * 2))
    if size > 8192:
        raise ValueError("目标窗口超过 8192 像元。请拆分目标或缩小框选范围。")
    if not expand:
        # Prefer an existing full-preparation tile for any prompt group it contains.
        col=int((min(xs)+max(xs))/2)//768*768-128
        row=int((min(ys)+max(ys))/2)//768*768-128
        if min(xs)>=col and max(xs)<col+1024 and min(ys)>=row and max(ys)<row+1024:
            return (col,row,1024,1024)
    return (math.floor((min(xs)+max(xs))/2-size/2), math.floor((min(ys)+max(ys))/2-size/2), size, size)
