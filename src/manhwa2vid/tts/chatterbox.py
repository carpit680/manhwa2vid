"""Local Chatterbox TTS (GPU-accelerated)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.console import Console

from manhwa2vid.config import get_nested
from manhwa2vid.tts.provider import TTSProvider, resolve_voice_prompt

console = Console()

_model: Any = None
_model_key: str | None = None


def _resolve_device(config: dict[str, Any]) -> str:
    configured = get_nested(config, "tts", "device")
    if configured:
        return str(configured)
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
    except ImportError:
        pass
    return "cpu"


def _load_model(config: dict[str, Any]) -> Any:
    global _model, _model_key
    preferred = _resolve_device(config)
    model_name = get_nested(config, "tts", "model", default="standard")

    for device in [preferred, "cpu"] if preferred != "cpu" else ["cpu"]:
        key = f"{model_name}:{device}"
        if _model is not None and _model_key == key:
            return _model
        try:
            console.print(f"[dim]Loading Chatterbox model ({model_name}) on {device}...[/]")
            if model_name == "turbo":
                from chatterbox.tts_turbo import ChatterboxTurboTTS

                model = ChatterboxTurboTTS.from_pretrained(device=device)
            elif model_name == "multilingual":
                from chatterbox.mtl_tts import ChatterboxMultilingualTTS

                model = ChatterboxMultilingualTTS.from_pretrained(device=device)
            else:
                from chatterbox.tts import ChatterboxTTS

                model = ChatterboxTTS.from_pretrained(device=device)
            _model = model
            _model_key = key
            if device == "cpu" and preferred != "cpu":
                console.print(
                    "[yellow]GPU unavailable for this PyTorch build (RTX 5070 needs cu128). "
                    "Using CPU — install nightly: "
                    "pip install --pre torch torchaudio --index-url "
                    "https://download.pytorch.org/whl/nightly/cu128[/]"
                )
            return _model
        except RuntimeError as exc:
            if device == "cpu" or "CUDA" not in str(exc):
                raise
            console.print(f"[yellow]CUDA failed ({exc}); retrying on CPU...[/]")
    raise RuntimeError("Failed to load Chatterbox model")


class ChatterboxTTSProvider(TTSProvider):
    def synthesize(self, text: str, out_path: Path, config: dict[str, Any]) -> None:
        import soundfile as sf
        import torch

        model = _load_model(config)
        out_wav = out_path.with_suffix(".wav")
        out_wav.parent.mkdir(parents=True, exist_ok=True)

        model_name = get_nested(config, "tts", "model", default="standard")
        prompt = resolve_voice_prompt(config)
        if model_name == "turbo" and not prompt:
            raise RuntimeError(
                "Chatterbox Turbo requires a reference voice clip. "
                "Set tts.voice_prompt in config.yaml to a ~5-10s WAV file."
            )

        kwargs: dict[str, Any] = {
            "exaggeration": float(get_nested(config, "tts", "exaggeration", default=0.7)),
        }
        if prompt:
            kwargs["audio_prompt_path"] = str(prompt)
        if model_name == "multilingual":
            kwargs["language_id"] = get_nested(config, "tts", "language_id", default="en")

        cfg_weight = float(get_nested(config, "tts", "cfg_weight", default=0.5))
        wav = None
        for cfg_key in ("cfg_weight", "cfg"):
            try:
                wav = model.generate(text, **kwargs, **{cfg_key: cfg_weight})
                break
            except TypeError:
                continue
        if wav is None:
            wav = model.generate(text, **kwargs)

        audio = wav.detach().cpu().numpy() if torch.is_tensor(wav) else wav
        if audio.ndim > 1:
            audio = audio.squeeze()
        sf.write(str(out_wav), audio, model.sr)

        from manhwa2vid.tts.postprocess import apply_tts_postprocess

        apply_tts_postprocess(out_wav, config)
