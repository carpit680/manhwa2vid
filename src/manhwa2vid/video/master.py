"""The mastering chain: narration and music bed into one broadcast-ready track.

`docs/audio-quality-spec.md` §5. Replaces a flat `amix` of a voice track and a bed held
at a fixed volume, which measured (2026-08-28) as a wall: loudness range 2.0-2.3 LU with
the bed sitting 19.5 dB under the narration — technically present, audibly absent.

Two properties this file exists to guarantee:

* **One graph, built once, used twice.** Two-pass `loudnorm` only works if pass two
  normalizes the same signal pass one measured. The previous code split those passes
  across two functions and an intermediate AAC encode, so pass one measured something
  that no longer existed by the time pass two ran.
* **Order is not arbitrary.** Pitch shift before EQ, so the EQ acts on the final spectrum;
  compression after EQ; de-essing after compression, because pitching down accentuates
  sibilance; loudness last.
"""

from __future__ import annotations

from typing import Any

from manhwa2vid.config import get_nested

# Voice chain. Each stage earns its place in docs/audio-quality-spec.md §5's table; the
# short version is in the comments below.
_VOICE_CHAIN = (
    "aformat=sample_fmts=fltp:channel_layouts=mono:sample_rates=48000",
    # Sub-speech rumble eats headroom and muddies the bed mix.
    "highpass=f=75:p=2:width_type=q:width=0.707",
    "{pitch}"
    # 240/450/950 are mud and boxiness. Cutting here does more for perceived depth than
    # boosting bass does.
    "equalizer=f=240:width_type=q:width=1.2:g=-3",
    "equalizer=f=450:width_type=q:width=1.5:g=-2",
    "equalizer=f=950:width_type=q:width=2.5:g=-2.5",
    "bass=f=115:width_type=q:width=0.7:g=2.5:p=2",        # chest weight, below the mud
    "equalizer=f=3100:width_type=q:width=0.9:g=2.5",      # presence: consonants
    "treble=f=9000:width_type=q:width=0.7:g=1.5:p=2",     # air; TTS has little real HF
    # 15 ms attack keeps consonant transients, 220 ms release avoids pumping.
    "acompressor=threshold=-20dB:ratio=2.5:attack=15:release=220:knee=4:makeup=1.6:detection=rms",
    "deesser=i=0.12:m=0.4:f=0.6:s=o",
    # TTS is unnaturally dry; 7% wet early reflection reads as "recorded in a place".
    "aecho=in_gain=0.92:out_gain=0.07:delays=23|37:decays=0.11|0.07",
)

# -1.5 semitones with formants preserved: 2^(-1.5/12) = 0.917. This is where depth comes
# from, and unlike a voice blend it is one reversible number. asetrate+atempo would shift
# formants and produce the giant/chipmunk effect instead.
_PITCH_FILTER = (
    "rubberband=pitch={pitch}:formant=preserved:pitchq=quality:transients=smooth"
    ":detector=soft:phase=independent:window=standard:smoothing=off:channels=together,"
)

_BED_CHAIN = (
    "aformat=sample_fmts=fltp:channel_layouts=mono:sample_rates=48000",
    "highpass=f=60:p=2",
    "equalizer=f=2500:width_type=q:width=1.0:g=-3",   # carve room for the voice
)


def build_filter(
    config: dict[str, Any],
    *,
    pad_seconds: float,
    with_bed: bool,
    loudnorm: str,
) -> str:
    """The complete filter_complex. Inputs: [1:a] narration, [2:a] bed (when present).

    `loudnorm` is the only part that differs between the measuring pass and the rendering
    pass, which is the whole point of building the graph in one place.
    """
    semitones = float(get_nested(config, "video", "voice_pitch_semitones", default=-1.5))
    pitch = _PITCH_FILTER.format(pitch=round(2 ** (semitones / 12.0), 4)) if semitones else ""
    voice = ",".join(_VOICE_CHAIN).format(pitch=pitch)
    pad = f",apad=pad_dur={max(pad_seconds, 0.0)}" if pad_seconds > 0 else ""

    if not with_bed:
        return f"[1:a]{voice}{pad},{loudnorm}[aout]"

    bed_db = float(get_nested(config, "video", "bgm_gain_db", default=-30.0))
    # Ducking is measured, not eyeballed: `bgm_gain_db` is the one number to turn until
    # the audio-duck-depth gate reads 12-15 dB. The old linear `bgm_volume` is gone —
    # two controls fighting over the same level is how it ended up 19.5 dB down.
    return (
        f"[1:a]{voice}{pad},asplit=2[v_mix][v_key];"
        f"[2:a]{','.join(_BED_CHAIN)},volume={bed_db}dB,aloop=loop=-1:size=2e+09[bed];"
        f"[bed][v_key]sidechaincompress=threshold=0.01:ratio=10:attack=20:release=350"
        f":makeup=1:knee=2.83:detection=rms[bed_duck];"
        f"[v_mix][bed_duck]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,"
        # Catch inter-sample peaks BEFORE loudnorm, not after: alimiter after normalization
        # re-introduces exactly the overshoot loudnorm just removed.
        f"alimiter=limit=0.9:attack=5:release=60:asc=1,"
        f"{loudnorm}[aout]"
    )


def measure_pass(target: float, lra: float) -> str:
    return f"loudnorm=I={target}:TP=-1.5:LRA={lra}:print_format=json"


def render_pass(target: float, lra: float, measured: dict[str, str]) -> str:
    """Pass two, linear, using pass one's measurements of the IDENTICAL graph."""
    return (
        f"loudnorm=I={target}:TP=-1.5:LRA={lra}:linear=true"
        f":measured_I={measured['input_i']}:measured_TP={measured['input_tp']}"
        f":measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}"
        f":offset={measured['target_offset']}"
    )
