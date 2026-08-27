"""Optional 2x anime upscale for panels before render.

Source art on both real projects is 720-800px wide; a 1080p fill-frame window is a
2.4-2.7x Lanczos blowup, soft everywhere. Real-ESRGAN's anime model recovers line
crispness that Lanczos cannot. Everything here is best-effort: no model, no GPU, or no
spandrel means the render silently keeps the original panels — sharpness is an upgrade,
never a dependency.

Weights: RealESRGAN_x4plus_anime_6B (17MB), fetched once into ~/.cache/manhwa2vid/.
The model is x4; output is downsized to the configured scale (default 2x) so a 10,000px
strip does not become a 40,000px memory bomb. Tall strips are processed in overlapping
horizontal bands for the same reason.
"""

from __future__ import annotations

import urllib.request
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from rich.console import Console

from manhwa2vid.config import get_nested

console = Console()

_MODEL_URL = (
    "https://github.com/xinntao/Real-ESRGAN/releases/download/"
    "v0.2.2.4/RealESRGAN_x4plus_anime_6B.pth"
)
_MODEL_CACHE = Path.home() / ".cache" / "manhwa2vid" / "RealESRGAN_x4plus_anime_6B.pth"

_loaded_model = None  # process-lifetime cache


def _load_model():
    global _loaded_model
    if _loaded_model is not None:
        return _loaded_model
    import torch
    from spandrel import ModelLoader

    if not _MODEL_CACHE.exists():
        _MODEL_CACHE.parent.mkdir(parents=True, exist_ok=True)
        console.print(f"[dim]Fetching upscale weights → {_MODEL_CACHE.name}[/]")
        tmp = _MODEL_CACHE.with_suffix(".tmp")
        urllib.request.urlretrieve(_MODEL_URL, tmp)
        tmp.replace(_MODEL_CACHE)

    model = ModelLoader().load_from_file(_MODEL_CACHE)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.to(device).eval()
    _loaded_model = (model, device)
    return _loaded_model


def _upscale_array(arr: np.ndarray, band_px: int = 512, overlap: int = 16) -> np.ndarray:
    """Run the x4 model over an RGB uint8 array in overlapping horizontal bands.

    Webtoon strips run to 800x10000+; a single forward pass at x4 would not fit an
    8GB card, so bands are processed independently and the overlap rows discarded —
    seams land inside content the neighbouring band also produced.
    """
    import torch

    model, device = _load_model()
    h, w = arr.shape[:2]
    out_scale = 4
    out = np.zeros((h * out_scale, w * out_scale, 3), dtype=np.uint8)
    y = 0
    while y < h:
        y0 = max(0, y - overlap)
        y1 = min(h, y + band_px + overlap)
        band = arr[y0:y1]
        tensor = (
            torch.from_numpy(band.astype(np.float32) / 255.0)
            .permute(2, 0, 1)
            .unsqueeze(0)
            .to(device)
        )
        with torch.no_grad():
            result = model(tensor)
        band_out = (
            result.squeeze(0).permute(1, 2, 0).clamp(0, 1).mul(255).byte().cpu().numpy()
        )
        keep0 = (y - y0) * out_scale
        keep1 = keep0 + (min(h, y + band_px) - y) * out_scale
        out[y * out_scale : y * out_scale + (keep1 - keep0)] = band_out[keep0:keep1]
        y += band_px
    return out


def upscaled_panels_dir(project_root: Path) -> Path:
    return project_root / "panels_2x"


def _cache_is_fresh(src: Path, cached: Path, scale: int) -> bool:
    """Does this cached 2x image still correspond to the panel of that name?

    Presence alone is NOT enough, and this cost four renders before it was noticed.
    Panel ids are POSITIONAL (pNNNN_MM), so re-running the panels stage reassigns them:
    after a 2026-08-26 re-split, 64 of Frozen Player's 172 cached upscales held a
    completely different picture from the panel of the same name, and every render since
    had been quietly compositing the old image while the timeline named the new one.
    Nothing downstream could see it — the timeline, the gates and the durations were all
    self-consistent, and only opening a frame and comparing it to its panel showed it.

    Two independent checks, either of which would have caught that case: the panel must
    not be newer than its cache, and the cache must be exactly `scale` times its size.
    """
    try:
        if cached.stat().st_mtime < src.stat().st_mtime:
            return False
        with Image.open(src) as a, Image.open(cached) as b:
            return b.size == (a.size[0] * scale, a.size[1] * scale)
    except (OSError, ValueError):
        return False


def upscale_panels(
    panel_paths: list[Path],
    project_root: Path,
    config: dict[str, Any],
) -> dict[str, Path]:
    """Ensure 2x versions exist for the given panels; return {original name -> 2x path}.

    Cached, but VALIDATED — see `_cache_is_fresh`; presence alone silently served a
    different picture after a re-split. Any failure (missing spandrel, no weights, CUDA
    OOM) logs once and returns what exists; the render falls back to the originals for
    the rest.
    """
    # Env wins over config (tests/conftest.py sets it off suite-wide); code default is
    # OFF so bare configs never touch the model — config.yaml enables real projects.
    import os

    env = os.getenv("MANHWA2VID_UPSCALE")
    enabled = (
        env not in ("0", "false", "off")
        if env is not None
        else bool(get_nested(config, "video", "upscale", "enabled", default=False))
    )
    if not enabled:
        return {}
    scale = int(get_nested(config, "video", "upscale", "scale", default=2))
    out_dir = upscaled_panels_dir(project_root)
    out_dir.mkdir(exist_ok=True)

    mapping: dict[str, Path] = {}
    todo: list[Path] = []
    stale = 0
    for p in panel_paths:
        out = out_dir / p.name
        if out.exists() and _cache_is_fresh(p, out, scale):
            mapping[p.name] = out
        else:
            stale += out.exists()
            todo.append(p)
    if stale:
        console.print(f"[yellow]{stale} cached upscale(s) no longer match their panel — redoing[/]")
    if not todo:
        return mapping

    try:
        _load_model()
    except Exception as exc:  # noqa: BLE001 — sharpness is optional, never fatal
        console.print(f"[yellow]Upscale unavailable ({exc}) — rendering at native resolution[/]")
        return mapping

    console.print(f"[dim]Upscaling {len(todo)} panel(s) x{scale}…[/]")
    for p in todo:
        try:
            arr = np.asarray(Image.open(p).convert("RGB"))
            up = _upscale_array(arr)
            if scale != 4:
                target = (arr.shape[1] * scale, arr.shape[0] * scale)
                up_img = Image.fromarray(up).resize(target, Image.Resampling.LANCZOS)
            else:
                up_img = Image.fromarray(up)
            out = out_dir / p.name
            up_img.save(out)
            mapping[p.name] = out
        except Exception as exc:  # noqa: BLE001
            console.print(f"[yellow]Upscale failed for {p.name} ({exc}) — using original[/]")
    return mapping
