"""Exercise GeoForma dependencies without downloading model weights.

Run with the GeoForma Python interpreter. Test data lives in a temporary folder.
The SAM smoke test uses random weights and does not evaluate segmentation quality.
"""

from __future__ import annotations

import importlib.metadata
import json
import sys
import tempfile
import time
import traceback
from pathlib import Path


def check_qt():
    from PySide6 import QtCore
    from PySide6.QtWidgets import QApplication, QLabel

    app = QApplication.instance() or QApplication([])
    widget = QLabel("GeoForma UI smoke test")
    widget.resize(320, 80)
    app.processEvents()
    assert not widget.grab().isNull()
    widget.close()
    designer_candidates = [Path(QtCore.QLibraryInfo.path(
                               QtCore.QLibraryInfo.LibraryPath.BinariesPath)) / "designer.exe",
                           Path(sys.prefix) / "Library/bin/designer.exe",
                           Path(sys.prefix) / "Lib/site-packages/PySide6/designer.exe"]
    designer = next((p for p in designer_candidates if p.is_file()), None)
    assert designer is not None, f"Designer missing: {designer_candidates}"
    return {"qt": QtCore.qVersion(), "platform": app.platformName(),
            "designer": str(designer)}


def check_geo():
    import numpy as np
    import rasterio
    from rasterio.features import rasterize, shapes
    from rasterio.transform import Affine
    from rasterio.windows import Window
    from osgeo import gdal, ogr, osr
    from shapely.geometry import shape

    gdal.UseExceptions()
    ogr.UseExceptions()
    transform = Affine(2, 0.2, 500000, 0.1, -2, 4000000)
    pixels = np.arange(48 * 64, dtype=np.uint16).reshape(48, 64)
    with tempfile.TemporaryDirectory(prefix="GeoForma_unicode path_") as folder:
        root = Path(folder)
        tif = root / "\u5f71\u50cf test.tif"
        with rasterio.open(tif, "w", driver="GTiff", width=64, height=48,
                           count=1, dtype="uint16", crs="EPSG:32650",
                           transform=transform, nodata=65535) as dst:
            dst.write(pixels, 1)
        with rasterio.open(tif) as src:
            assert np.array_equal(src.read(1, window=Window(5, 7, 11, 13)),
                                  pixels[7:20, 5:16])
        vrt = root / "\u76f8\u5bf9\u5f15\u7528.vrt"
        vrt.write_text('<VRTDataset rasterXSize="64" rasterYSize="48">'
                       '<SRS>EPSG:32650</SRS>'
                       '<GeoTransform>500000,2,0.2,4000000,0.1,-2</GeoTransform>'
                       '<VRTRasterBand dataType="UInt16" band="1">'
                       '<SimpleSource><SourceFilename relativeToVRT="1">'
                       '\u5f71\u50cf test.tif</SourceFilename><SourceBand>1</SourceBand>'
                       '<SrcRect xOff="0" yOff="0" xSize="64" ySize="48"/>'
                       '<DstRect xOff="0" yOff="0" xSize="64" ySize="48"/>'
                       '</SimpleSource></VRTRasterBand></VRTDataset>', encoding="utf-8")
        with rasterio.open(vrt) as src:
            assert np.array_equal(src.read(1), pixels)
            assert src.transform == transform
            assert src.crs.to_epsg() == 32650
        mask = np.zeros((48, 64), dtype=np.uint8)
        mask[4:20, 5:24] = 1
        mask[8:11, 9:13] = 0
        mask[40, 55] = 1
        geometries = list(shapes(mask, mask=mask.astype(bool), transform=transform))
        assert all(shape(geometry).is_valid for geometry, _ in geometries)
        restored = rasterize(geometries, out_shape=mask.shape, transform=transform,
                             dtype="uint8", all_touched=False)
        assert np.array_equal(mask, restored)
        gpkg = root / "\u6807\u7b7e test.gpkg"
        # GDAL 3.13.3's optional feature-count cache was stale after rollback
        # in this environment. Disable that extension, not transactions.
        ds = ogr.GetDriverByName("GPKG").CreateDataSource(
            str(gpkg), options=["ADD_GPKG_OGR_CONTENTS=NO"])
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(32650)
        layer = ds.CreateLayer("labels", srs, ogr.wkbPolygon)
        layer.CreateField(ogr.FieldDefn("class_id", ogr.OFTInteger))
        assert ds.StartTransaction() == 0
        for geometry, _ in geometries:
            feature = ogr.Feature(layer.GetLayerDefn())
            feature.SetField("class_id", 1)
            feature.SetGeometry(ogr.CreateGeometryFromJson(json.dumps(geometry)))
            assert layer.CreateFeature(feature) == 0
            feature = None
        assert ds.CommitTransaction() == 0
        assert ds.StartTransaction() == 0
        assert layer.DeleteFeature(1) == 0
        assert ds.RollbackTransaction() == 0
        layer = None
        ds = None
        ds = ogr.Open(str(gpkg))
        actual_count = ds.GetLayer(0).GetFeatureCount()
        actual_ids = [item.GetFID() for item in ds.GetLayer(0)]
        ds.Close()
        ds = None
        assert actual_count == len(geometries), (actual_count, len(geometries))
        assert len(actual_ids) == len(geometries) and 1 in actual_ids
    return {"rasterio_gdal": rasterio.__gdal_version__,
            "ogr_gdal": gdal.VersionInfo("RELEASE_NAME"),
            "gpkg_creation_options": ["ADD_GPKG_OGR_CONTENTS=NO"],
            "checks": ["unicode_paths", "window_read", "relative_vrt",
                       "rotated_grid_mask_roundtrip", "gpkg_commit_and_rollback"]}


def check_torch():
    import torch
    from torchvision.ops import nms

    result = {"torch": torch.__version__, "cuda_runtime": torch.version.cuda,
              "cuda_available": torch.cuda.is_available()}
    assert torch.cuda.is_available(), "Expected the installed NVIDIA GPU to be available"
    result["gpu"] = torch.cuda.get_device_name(0)
    for device in ("cpu", "cuda"):
        matrix = torch.eye(32, device=device)
        assert torch.equal(matrix @ matrix, matrix)
        boxes = torch.tensor([[0, 0, 10, 10], [1, 1, 9, 9]],
                             dtype=torch.float32, device=device)
        scores = torch.tensor([0.9, 0.8], device=device)
        assert nms(boxes, scores, 0.5).tolist() == [0]
    torch.cuda.synchronize()
    return result


def check_sam():
    import numpy as np
    import torch
    from segment_anything import SamAutomaticMaskGenerator, SamPredictor, sam_model_registry

    torch.manual_seed(0)
    model = sam_model_registry["vit_b"]().eval().to("cuda")
    predictor = SamPredictor(model)
    counts = {"image_encoder_calls": 0}

    def count_encoder(*_args):
        counts["image_encoder_calls"] += 1

    hook = model.image_encoder.register_forward_hook(count_encoder)
    with torch.inference_mode():
        predictor.set_image(np.zeros((128, 192, 3), dtype=np.uint8))
        masks, scores, logits = predictor.predict(
            point_coords=np.array([[96, 64]], dtype=np.float32),
            point_labels=np.array([1]), multimask_output=True)
        assert masks.shape == (3, 128, 192)
        choice = int(scores.argmax())
        refined, _, _ = predictor.predict(
            point_coords=np.array([[96, 64], [10, 10]], dtype=np.float32),
            point_labels=np.array([1, 0]), mask_input=logits[choice:choice + 1],
            multimask_output=False)
        assert refined.shape == (1, 128, 192)
        assert counts["image_encoder_calls"] == 1
        embedding_shape = list(predictor.get_image_embedding().shape)
        generator = SamAutomaticMaskGenerator(model, points_per_side=2,
                                              points_per_batch=4, crop_n_layers=0)
        candidates = generator.generate(np.zeros((64, 96, 3), dtype=np.uint8))
        assert counts["image_encoder_calls"] == 2
    hook.remove()
    del predictor, generator, model
    torch.cuda.empty_cache()
    return {**counts, "embedding_shape": embedding_shape,
            "automatic_candidates": len(candidates),
            "weights": "RANDOM: API/device smoke test only, no pretrained weights"}


def main():
    report = {"python": sys.version, "executable": sys.executable, "checks": {}}
    failed = False
    for name, check in (("qt", check_qt), ("geo", check_geo),
                        ("torch", check_torch), ("sam", check_sam)):
        started = time.perf_counter()
        try:
            details = check()
            report["checks"][name] = {"ok": True, "details": details}
        except Exception:
            failed = True
            report["checks"][name] = {"ok": False, "error": traceback.format_exc()}
        report["checks"][name]["seconds"] = round(time.perf_counter() - started, 2)
        print(json.dumps({name: report["checks"][name]}, ensure_ascii=False), flush=True)
    report["ok"] = not failed
    destination = Path(__file__).with_name("verification.json")
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
