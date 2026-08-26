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


def upscale_panels(
    panel_paths: list[Path],
    project_root: Path,
    config: dict[str, Any],
) -> dict[str, Path]:
    """Ensure 2x versions exist for the given panels; return {original name -> 2x path}.

    Cached by file presence — re-renders cost nothing. Any failure (missing spandrel,
    no weights, CUDA OOM) logs once and returns what exists; the render falls back to
    the originals for the rest.
    """
    # Default OFF in code so offline tests and bare configs never touch the model;
    # config.yaml turns it on for real projects.
    if not bool(get_nested(config, "video", "upscale", "enabled", default=False)):
        return {}
    scale = int(get_nested(config, "video", "upscale", "scale", default=2))
    out_dir = upscaled_panels_dir(project_root)
    out_dir.mkdir(exist_ok=True)

    mapping: dict[str, Path] = {}
    todo: list[Path] = []
    for p in panel_paths:
        out = out_dir / p.name
        if out.exists():
            mapping[p.name] = out
        else:
            todo.append(p)
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
