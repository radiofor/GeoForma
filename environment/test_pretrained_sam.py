"""Real-weight SAM checks; no training or production application code."""

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image
import numpy as np
import torch
from segment_anything import SamAutomaticMaskGenerator, SamPredictor, sam_model_registry

from prepare_sam import COMMIT, data_root


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load_model(path, device):
    model = sam_model_registry["vit_b"]()
    # Explicit restricted deserialization, followed by strict tensor matching.
    model.load_state_dict(torch.load(path, map_location="cpu", weights_only=True), strict=True)
    return model.eval().to(device)


def restore(predictor, cache, identity, device):
    # Engineering adapter for this pinned original SAM revision only.
    # Official SamPredictor does not expose an on-disk cache restore API.
    if cache["identity"] != identity:
        raise ValueError("Cache identity mismatch")
    features = cache["features"]
    if tuple(features.shape) != (1, 256, 64, 64) or features.dtype != torch.float32:
        raise ValueError("Unexpected embedding format")
    predictor.reset_image()
    predictor.features = features.to(device)
    predictor.original_size = tuple(cache["original_size"])
    predictor.input_size = tuple(cache["input_size"])
    predictor.is_image_set = True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-only", action="store_true")
    args = parser.parse_args()
    torch.set_num_threads(8)
    root = data_root()
    output = root / "test_results"
    output.mkdir(parents=True, exist_ok=True)
    checkpoint = root / "models/sam_vit_b_01ec64.pth"
    sample = root / "samples/truck.jpg"
    image = np.array(Image.open(sample).convert("RGB"))
    identity = {"backend": "meta_sam", "commit": COMMIT, "model": "vit_b",
                "weights_sha256": sha256(checkpoint), "image_sha256": sha256(sample),
                "preprocessing": "RGB uint8; official ResizeLongestSide(1024); FP32",
                "window_xywh": [0, 0, image.shape[1], image.shape[0]], "schema": 1}
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = load_model(checkpoint, device)
    count = [0]
    def encoded(*_):
        count[0] += 1
    hook = model.image_encoder.register_forward_hook(encoded)
    predictor = SamPredictor(model)
    prompts = {"point_coords": np.array([[500, 375]], dtype=np.float32),
               "point_labels": np.array([1]), "multimask_output": True}
    cache_path = output / "truck_embedding.pt"
    if args.cache_only:
        with torch.inference_mode():
            restore(predictor, torch.load(cache_path, weights_only=True, map_location="cpu"), identity, device)
            masks, scores, logits = predictor.predict(**prompts)
        np.savez(output / "fresh_process_prediction.npz", masks=masks, scores=scores, logits=logits)
        assert count[0] == 0
        print("Fresh-process cache prediction passed without image encoding", flush=True)
        return

    report = {"identity": identity, "python": sys.version, "torch": torch.__version__,
              "device": device, "gpu": torch.cuda.get_device_name(0) if device == "cuda" else None,
              "scope": "Official truck example; not a remote-sensing accuracy benchmark", "timings_seconds": {}}
    def timed(name, fn):
        if device == "cuda": torch.cuda.synchronize()
        start = time.perf_counter()
        result = fn()
        if device == "cuda": torch.cuda.synchronize()
        report["timings_seconds"][name] = round(time.perf_counter() - start, 4)
        print(name, report["timings_seconds"][name], flush=True)
        return result

    with torch.inference_mode():
        timed("encode", lambda: predictor.set_image(image))
        masks, scores, logits = timed("first_point", lambda: predictor.predict(**prompts))
        assert masks.shape == (3, *image.shape[:2]) and np.isfinite(scores).all()
        choice = int(scores.argmax())
        assert masks[choice].any() and not masks[choice].all()
        refined, _, _ = timed("refine", lambda: predictor.predict(
            point_coords=np.array([[500, 375], [1125, 625]], dtype=np.float32),
            point_labels=np.array([1, 0]), mask_input=logits[choice:choice+1], multimask_output=False))
        boxed, _, _ = timed("box", lambda: predictor.predict(
            box=np.array([425, 600, 700, 875], dtype=np.float32), multimask_output=False))
        assert refined.shape == boxed.shape == (1, *image.shape[:2])
        assert count[0] == 1
        report["interactive_encoder_calls"] = count[0]
        cache = {"identity": identity, "features": predictor.get_image_embedding().cpu(),
                 "original_size": list(predictor.original_size), "input_size": list(predictor.input_size)}
        torch.save(cache, cache_path)
        reloaded = SamPredictor(model)
        restore(reloaded, torch.load(cache_path, weights_only=True, map_location="cpu"), identity, device)
        cached_masks, cached_scores, cached_logits = timed("cached_point", lambda: reloaded.predict(**prompts))
        assert np.array_equal(cached_masks, masks)
        assert np.allclose(cached_logits, logits, atol=1e-5)
        assert count[0] == 1
        invalid = dict(identity, schema=999)
        try:
            restore(reloaded, cache, invalid, device)
        except ValueError:
            report["cache_invalidation_passed"] = True
        else:
            raise AssertionError("Mismatched cache accepted")
        generator = SamAutomaticMaskGenerator(model, points_per_side=4, points_per_batch=16, crop_n_layers=0)
        candidates = timed("automatic_4x4", lambda: generator.generate(image))
        assert count[0] == 2
        report["automatic_candidates"] = len(candidates)
        report["automatic_additional_encoder_calls"] = 1
        report["scores"] = scores.tolist()
        report["cache_bytes"] = cache_path.stat().st_size
        report["peak_cuda_allocated_mib"] = round(torch.cuda.max_memory_allocated()/1024**2, 1) if device == "cuda" else None

    subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()), "--cache-only"], check=True, timeout=180)
    with np.load(output / "fresh_process_prediction.npz") as fresh:
        assert np.array_equal(masks, fresh["masks"])
        assert np.allclose(logits, fresh["logits"], atol=1e-5)
    report["fresh_process_cache_equal"] = True
    hook.remove()
    # Verify full CPU encoding plus decoding, not just a CPU tensor operation.
    model.to("cpu")
    cpu = SamPredictor(model)
    cpu_start = time.perf_counter()
    with torch.inference_mode():
        cpu.set_image(image)
        cpu_masks, cpu_scores, _ = cpu.predict(**prompts)
    assert cpu_masks.shape == masks.shape and np.isfinite(cpu_scores).all()
    report["cpu_full_inference_seconds"] = round(time.perf_counter() - cpu_start, 3)
    report["cpu_inference_passed"] = True
    overlay = image.copy()
    selected = masks[choice]
    overlay[selected] = (0.55 * overlay[selected] + 0.45 * np.array([0, 190, 255])).astype(np.uint8)
    Image.fromarray(overlay).save(output / "truck_point_overlay.png")
    Image.fromarray(selected.astype(np.uint8)*255).save(output / "truck_point_mask.png")
    Image.fromarray(refined[0].astype(np.uint8)*255).save(output / "truck_refined_mask.png")
    report["ok"] = True
    destination = Path(__file__).with_name("pretrained_sam_report.json")
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
