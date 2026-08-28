# Audio quality spec — voice, pronunciation, mastering

Concrete configuration for the narration stage.

**How to use this document.** It has one finding that is verified and one that is not, and
they are marked. §0 is a reproduction procedure with a human-in-the-loop gate at §0.6 — run
it before changing any pipeline code. §§1–5 are configuration recommendations traceable to
the Kokoro/misaki source or to cited measurement; where evidence is absent the text says so.
§6 lists gates to add, §7 the order of work.

**Environment the §0 finding was produced in:** kokoro 0.9.4, misaki 0.9.4, torch 2.13.0,
spacy 3.8.16, en_core_web_sm 3.8.0, phonemizer-fork 3.3.2, espeakng-loader 0.2.4,
eSpeak NG 1.51, Python 3.11.15, Linux x86_64, CPU. `pyproject.toml` pins only `kokoro>=0.9`,
so **record what actually resolves on this machine first** — §0.3 Script 1 does that.

**Rules for the implementing agent:**
- Verify before you build. Every §0 claim is falsifiable; if a number here is wrong on this
  machine, correct it in writing rather than coding around it.
- Do not integrate before the §0.6 gate passes, including the human listening step.
- No gate ships without a test that feeds it a deliberately broken input and asserts failure.
- Do not weaken a threshold to make a render pass.
- `tests/test_offline_guard.py` must keep passing.

---

## 0. Pronunciation: verified finding + reproduction procedure

> **STATUS: verified at the phoneme layer, NOT at the audio layer.**
> An agent implementing this must run §0.3 (audio A/B) with the user listening, and must
> NOT integrate into the pipeline until the user confirms the audio difference. See §0.6.

### 0.1 Provenance — exact environment the finding was produced in

Produced 2026-08-28 in a clean Linux x86_64 container, Python 3.11.15, CPU only:

```
kokoro==0.9.4          misaki==0.9.4         torch==2.13.0
spacy==3.8.16          en_core_web_sm==3.8.0 numpy==2.4.4
phonemizer-fork==3.3.2 espeakng-loader==0.2.4 soundfile==0.14.0
transformers==5.16.1   huggingface-hub==1.29.0
eSpeak NG 1.51
```

Install used:
```bash
pip install "misaki[en]" kokoro soundfile
apt-get install -y espeak-ng
pip install phonemizer-fork espeakng-loader
```

`pyproject.toml` currently pins only `kokoro>=0.9`. **Record the versions actually resolved
on this machine before trusting any number below**, and re-run §0.2 if they differ.

### 0.2 The mechanism, verified in the shipped wheel

`kokoro/pipeline.py:113` (kokoro 0.9.4):
```python
self.g2p = en.G2P(trf=trf, british=lang_code=='b', fallback=fallback, unk='')
```
misaki joins with `''.join((self.unk if tk.phonemes is None else tk.phonemes) + tk.whitespace ...)`,
so an unresolved token contributes an empty string. Kokoro's own log at `pipeline.py:110`:
```python
logger.warning("EspeakFallback not Enabled: OOD words will be skipped")
```

Kokoro builds an espeak fallback first and only lands on `fallback=None` if espeak-ng is
missing. **Two failure modes therefore exist. Determine which one applies here.**

**Path A — espeak-ng NOT installed: names are deleted.** Measured, 14 of 21 real names
produced empty or partial phonemes:

| Input | Output | Effect |
|---|---|---|
| `Jinwoo` `Baek` `Deok-Gu` `Carthenon` `Murim` | `''` | vanishes entirely |
| `Cha Hae-In` | `' hˈAˌɪn'` | becomes "Hae-In" |
| `Gong Chi-Yul` | `'ɡˈɔŋ kˈI'` | becomes "Gong Chai" |
| `Yeon Si-eun` | `' sˈi'` | becomes "See" |
| `Min Jung-woo` | `'mˈɪn wˈu'` | becomes "Min Woo" |

**Path B — espeak-ng installed (likely): names survive but are wrong.** Measured through a
live `KPipeline(lang_code='a')` with the fallback active:

```
BEFORE: ʧən jˈOˈʌn ænd mˈɪn jˈʊŋwˈu ˈɛntəɹd ðə kˈɑɹθɛnən tˈɛmpᵊl, ænd bˈik fˈɑlOd.
```
`Cheon Yeo-un` → "chun YO-un" · **`Min Jung-woo` → "min YUNG-woo"** (espeak turned J into Y)
· `Baek` → "beek" · `Gong Chi-Yul` → "gong KAI-yul" · `Murim` → "myoo-rim"

Path B is the more dangerous mode: fluent, confident, and **unstable across spellings** —
"Jung-woo" and "Jungwoo" can resolve differently, which is how one character acquires
several names across a video.

### 0.3 REPRODUCE — run these three scripts, in order

**Script 1 — establish this machine's environment and which path it is on.**

```python
# tools/qa/tts_env_check.py
import importlib.metadata as m, subprocess, shutil
for pkg in ["kokoro","misaki","torch","spacy","phonemizer-fork","espeakng-loader"]:
    try: print(f"{pkg}=={m.version(pkg)}")
    except Exception: print(f"{pkg}: NOT INSTALLED")
print("espeak-ng binary:", shutil.which("espeak-ng") or "NOT ON PATH")
from misaki import espeak
try:
    espeak.EspeakFallback(british=False); print("PATH B - espeak fallback AVAILABLE (names mispronounced)")
except Exception as e:
    print("PATH A - espeak fallback UNAVAILABLE (names DELETED):", repr(e)[:120])
```
Also: `grep -r "EspeakFallback not Enabled" <log dir>` — if present in past runs, those
renders were Path A.

**Script 2 — reproduce the G2P finding on this repo's real names.**

Read the character roster from the project `glossary.json` files rather than the hardcoded
list; fall back to this list if none exist.

```python
# tools/qa/tts_g2p_probe.py
import warnings; warnings.filterwarnings("ignore")
from misaki import en
NAMES = ["Jinwoo","Sung Jin-Woo","Cha Hae-In","Baek","Gong Chi-Yul","Deok-Gu","Shimuk",
         "Carthenon","Cheon Yeo-un","Chung Myung","Mu-won","Yeon Si-eun","Min Jung-woo",
         "Jun-Ho","Murim","manhwa"]
try:
    from misaki import espeak; fb = espeak.EspeakFallback(british=False)
except Exception: fb = None
g_del = en.G2P(trf=False, british=False, fallback=None, unk='')      # Path A
g_mrk = en.G2P(trf=False, british=False, fallback=None, unk='?UNK?') # shows what is unresolved
g_esp = en.G2P(trf=False, british=False, fallback=fb, unk='') if fb else None
for n in NAMES:
    a = g_del(n)[0]; mk = g_mrk(n)[0]; e = g_esp(n)[0] if g_esp else "<n/a>"
    print("%-15s deleted=%-24r espeak=%-26r unresolved=%s" % (n, a, e, "?UNK?" in mk))
```

**Script 3 — the audio A/B. THIS IS THE STEP THAT WAS NOT DONE.**

The finding above stops at the phoneme string. Phonemes are the model's direct input, so
correct phonemes should mean correct audio — but that was never rendered, because the
HuggingFace weight download was blocked in the test environment. **Render it here and have
the user listen.**

```python
# tools/qa/tts_ab_render.py
import warnings, numpy as np, soundfile as sf
warnings.filterwarnings("ignore")
from kokoro import KPipeline

SENT = "Cheon Yeo-un and Min Jung-woo entered the Carthenon temple, and Baek followed."
US_VOCAB = 'AIOWYbdfhijklmnpstuvwzæðŋɑɔəɛɜɡɪɹɾʃʊʌʒʤʧˈˌθᵊᵻʔ'
LEX = {"Cheon":"ʧˈʌn","Yeo":"jˈʌ","un":"ˈun","Min":"mˈɪn","Jung":"ʤˈʌŋ","woo":"wˈu",
       "Carthenon":"kˈɑɹθənɑn","Baek":"bˈɛk"}

p = KPipeline(lang_code='a')
print("espeak fallback:", p.g2p.fallback is not None)

def render(tag):
    outs = []
    for r in p(SENT, voice='am_michael', speed=1.0):
        print(f"[{tag}] {r.phonemes}")
        outs.append(r.audio.numpy() if hasattr(r.audio, "numpy") else np.asarray(r.audio))
    sf.write(f"_review/tts_{tag}.wav", np.concatenate(outs), 24000)

render("before")
for w, ps in LEX.items():
    bad = [c for c in ps if c not in US_VOCAB]
    assert not bad, f"{w}: illegal phonemes {bad}"
    for v in {w, w.lower(), w.upper(), w.capitalize()}:
        p.g2p.lexicon.golds[v] = ps
render("after")
```

**Expected phoneme output** (verified on 0.9.4 with espeak active — if this machine differs,
say so rather than proceeding):
```
before: ʧən jˈOˈʌn ænd mˈɪn jˈʊŋwˈu ˈɛntəɹd ðə kˈɑɹθɛnən tˈɛmpᵊl, ænd bˈik fˈɑlOd.
after : ʧˈʌn jˌʌˈun ænd mˈɪn ʤˈʌŋwˌu ˈɛntəɹd ðə kˈɑɹθənɑn tˈɛmpᵊl, ænd bˈɛk fˈɑlOd.
```

### 0.4 The lexicon

`p.g2p.lexicon.golds` is confirmed a mutable dict on a live `KPipeline` (178,646 entries at
0.9.4), consulted before espeak.

```python
US_VOCAB = 'AIOWYbdfhijklmnpstuvwzæðŋɑɔəɛɜɡɪɹɾʃʊʌʒʤʧˈˌθᵊᵻʔ'
LEX = {  # per-syllable, so hyphenation and word order generalise
 "Jinwoo":"ʤˈɪnwu","Jin":"ʤˈɪn","Woo":"wˈu","Cha":"ʧˈɑ","Baek":"bˈɛk",
 "Gong":"ɡˈɔŋ","Yul":"jˈul","Chi":"ʧˈi","Deok":"dˈʌk","Gu":"ɡˈu",
 "Shimuk":"ʃˈɪmuk","Carthenon":"kˈɑɹθənɑn","Cheon":"ʧˈʌn","Yeo":"jˈʌ",
 "un":"ˈun","Chung":"ʧˈʌŋ","Myung":"mjˈʌŋ","Mu":"mˈu","won":"wˈʌn",
 "Yeon":"jˈʌn","Si":"ʃˈi","eun":"ˈʌn","Jung":"ʤˈʌŋ",
 "Athanasia":"ˌæθənˈAʒə","Jae":"ʤˈɛ","hwan":"hwˈɑn","Murim":"mˈuɹɪm",
}
```
Validated 27/27 against `US_VOCAB`; 0/17 unresolved after injection. The validator assert
is **mandatory** — `Lexicon.__init__`'s own assert runs only at init, so post-hoc injections
are unvalidated and an illegal character is dropped silently downstream.

Case variants must be registered manually; `grow_dictionary()` only runs at init.

### 0.5 What is NOT proven — do not let this get lost

1. **No audio was ever rendered.** Blocked by egress on HuggingFace weights. Script 3 exists
   to close this. Until a human has listened, treat the audio claim as inference.
2. **The IPA is constructed from a romanisation mapping table, not by a Korean speaker.**
   It is clearly better than "beek" and "min YUNG-woo". It is not authoritative. Check a
   series roster against Wiktionary `Module:ko-pron` before committing it.
3. **Which path this install is on** — Script 1 settles it.
4. **Version drift** — findings are on 0.9.4/0.9.4. Script 1 records what is actually here.
5. **The name list was partly reconstructed** from audit reports and rendered frames, not
   read from `glossary.json`. Script 2 should read the real roster.

### 0.6 Integration gate — human in the loop

Do **not** wire any of this into the pipeline until, in this order:

1. Script 1 has run and the versions + path are recorded in the PR/commit message.
2. Script 2 has run and its output either matches §0.2 or the difference is explained.
3. Script 3 has produced `_review/tts_before.wav` and `_review/tts_after.wav`, and **the
   user has listened to both and confirmed the difference is real and an improvement.**
4. Only then: add `pronunciation` to the glossary schema, split `tts_text` from
   `subtitle_text` (§4), and add the `tts-phoneme-coverage` and `tts-lexicon-valid` gates.

If step 3 shows no audible improvement, stop and report — the phoneme-layer finding would
then be real but inconsequential, and that is a legitimate outcome worth knowing.

## 1. Voice selection

Grades and training volume from the model's own `VOICES.md`. Training-duration key:
`H hours` = 1–10h, `MM minutes` = 10–100min, `M minutes` = 1–10min.

| Voice | Target quality | Training | Overall |
|---|---|---|---|
| **am_michael** | B | **H hours** | **C+** |
| **am_fenrir** | B | **H hours** | **C+** |
| **am_puck** | B | **H hours** | **C+** |
| am_adam | D | H hours | **F+** |
| am_onyx | C | MM minutes | D |
| bm_fable / bm_george | B | MM minutes | C |
| bm_lewis | C | H hours | D+ |

**Switch off `am_adam`.** It carries the lowest grade of any English voice in the model —
the data volume is there but the reference audio and text/audio alignment are not.

**Use `am_michael`.** It is one of only three English male voices that are simultaneously
B-target-quality and H-hours. Data volume matters more than grade for this workload,
because robustness on rare phoneme sequences is exactly what a Korean name demands.

### Correction on blending

An earlier suggestion of an `am_michael:60,am_onyx:40` blend is withdrawn. Blending is
mechanically real — `KPipeline.load_voice` does `torch.mean(torch.stack(packs), dim=0)`
over any number of comma-separated voices, and `voice=` also accepts a raw CPU float32
tensor for weighted blends — but:

- **No community blend recipe for deep male narration exists.** No benchmark, no MOS study,
  no author guidance. Every "deep/authoritative" claim traces to unsourced SEO copy.
- **Averaging moves toward the mean**, which tends to reduce distinctiveness rather than
  add depth. Blending a C+/H-hours voice with a D/MM-minutes voice drags quality down.
- Depth is far better obtained in post, where it is a measurable, reversible parameter
  (§4). Use blending only to A/B *within* the {michael, fenrir, puck} trio, weights summing
  to 1, and only if a measured F0 test says it helps.

If blending: pass a **CPU float32** tensor. The guard is `isinstance(voice, torch.FloatTensor)`,
which a CUDA or fp16 tensor fails, falling through to `voice.split()` and an AttributeError.

### The measurement worth doing once

**No published F0 data exists for any Kokoro voice.** Render one 30-second passage across
all 13 English male voices at `speed=1.0`, measure median F0 and F0 range with
`praat-parselmouth` or `librosa.yin`, and pick on numbers. Twenty minutes of work that
replaces every adjective in every blog post on this subject.

---

## 2. Speed — the current setting is out of range

`config.yaml` runs `kokoro_speed: 1.34` against a `target_wpm` in the 220–235 band.

Kokoro's `speed` scales **predicted durations**, not the waveform, so pitch is preserved and
there is no chipmunk artefact — but it is asking the duration predictor to operate well
outside its training distribution, and the model card separately documents rushing above
~400 phonemes. Reported sane range is 0.5–2.0 with audiobook pacing at 0.9–0.95.

**Target `speed` 0.92–1.00.** Getting there without losing runtime is the same work as
closing the prose gap: `gap_vs_mamoru_2026-08-26.md` records the narration as 48% wordier
than the reference (1429 words vs 963 for the same two chapters). **Cut the word count and
the speed problem solves itself** — fewer words at a natural rate produces the same runtime,
closer reference prose density, and better audio, all at once.

`speed` also accepts a callable taking phoneme count, which is useful for taming long chunks:
```python
pipeline(text, voice=VOICE, speed=lambda n: 0.92 if n > 350 else 0.96)
```

---

## 3. Chunking — a non-obvious constraint

Voice packs are `[N, 1, 256]` tensors, N≈510, and the pipeline selects a style vector by
**phoneme count**: `model(ps, pack[len(ps)-1], speed, ...)`. The 256 dims split at 128 into
timbre (to the decoder) and prosody (to the duration/F0 predictor).

**Consequence: chunk length is a voice parameter.** The same voice at 40 phonemes and at
300 phonemes uses different style vectors and sounds measurably different. Wildly varying
chunk lengths across a 90-minute render produce audible timbre drift.

Rules:
- **Measure in phonemes, not characters**: `len(pipeline.g2p(chunk)[0])`.
- **Target 130–180 phonemes**, a deliberately tight band, split on sentence boundaries.
- Model card's goldilocks range is 100–200; below ~20 is weak, above ~400 rushes.
- Hard cap 510 (`max_position_embeddings: 512` minus 2). KPipeline truncates with a warning.
- Crossfade 20–30 ms at joins.

---

## 4. Pronunciation — building the entries

The mechanism, the validator and the verified lexicon are in §0. This section covers the
linguistics behind the entries and where they belong in this repo.

**Character traps** — these look right and are wrong:
- `ʤ` single char, **not** `dʒ`
- `ʧ` single char, **not** `tʃ`
- `ɹ` **not** ASCII `r`
- `ɡ` U+0261 script g, **not** ASCII `g`
- **no `ː`** — length mark is GB-only, absent from `US_VOCAB`
- **no `ɚ`** — in the model's 178-token vocab but not in `US_VOCAB`; write `ɜɹ` or `ɹ`

Diphthongs are single capitals: `A`=/eɪ/ `I`=/aɪ/ `O`=/oʊ/ `W`=/aʊ/ `Y`=/ɔɪ/.

### Korean romanisation → en-US phonemes

Revised Romanization is a keyboard transliteration, not a pronunciation guide, and its
digraphs collide head-on with English spelling rules. The worst offenders:

| RR | Hangul | Korean IPA | **Write as** | What English TTS does instead |
|---|---|---|---|---|
| **eo** | ㅓ | /ʌ/ | **`ʌ`** | /iːoʊ/ — *Leo, Theodore*. Worst offender. |
| **yeo** | ㅕ | /jʌ/ | **`jʌ`** | /jiːoʊ/ |
| **eu** | ㅡ | /ɯ/ | **`ə`** | /juː/ — *Europe* |
| **wo** | ㅝ | /wʌ/ | **`wʌ`** | /woʊ/ |
| **oe** | ㅚ | /ø/→[we] | **`wɛ`** | /oʊ/ — *toe* |
| **ui** | ㅢ | /ɰi/ | **`iː`** after a consonant | /uːɪ/ — *fluid* |
| ae | ㅐ | /ɛ/ | `ɛ` | /eɪ/ — *sundae* |
| e | ㅔ | /e/ | `ɛ` | /iː/ in open syllables |
| i | ㅣ | /i/ | `iː` | /aɪ/ in open syllables |
| u | ㅜ | /u/ | `uː` | /juː/ or /ʌ/ |
| o | ㅗ | /o/ | `oʊ` | usually fine |
| a | ㅏ | /a/ | `ɑ` | usually fine |

Consonants: `g`→`ɡ`, `d`→`d`, `b`→`b`, `j`→`ʤ`, `ch`→`ʧ`, `k/t/p`→`k/t/p` (English is
already aspirated initially), `r/l`→`ɹ` initially and `l` finally. Fortis `kk/tt/pp/ss/jj`
have no English equivalent — use the plain consonant.

**Hyphenated given names** (Jin-Woo, Yeo-un, Si-eun) are one prosodic word with light stress
on the first syllable: write `ʤˈɪnwu`, `jˈʌun`, `ʃˈiːʌn`.

### Sourcing the pronunciations

Romanised→IPA has no reliable tool and should not be built — romanisation is lossy in both
directions (`sung` could be 성/승/숭). The workable path, done once per series for a roster
of 10–40 names:

```
Hangul from the Korean source page → g2pK (sandhi) → Wiktionary Module:ko-pron or
epitran kor-Hang (Korean IPA) → map to en-US via the table above → validate → commit
```

An hour per series, fixes hundreds of utterances per video.

### Where it belongs in this repo

`glossary.json` and `characters/bible.py` already track every recurring name per series.
Add a `pronunciation` field alongside. **And split the text path** — `timeline.py:435` and
`engine.py:53` both read `beat.narration`, so today the SRT and the TTS get the same string
and any respelling would corrupt the captions. Add `tts_text` to `TimelineEntry` and to the
beat model, defaulting to `narration`; synthesise from `tts_text`, caption from
`subtitle_text`. Viewers then read "Cheon Yeo-un" and hear it said correctly.

---

## 5. Mastering chain

Current measured state: mono, 48 kHz, −16.4 LUFS integrated, LRA 2.3 LU, TP −1.4 dBTP,
music bed ducked 19.5 dB under narration.

Two-pass `loudnorm` is required — one-pass is a dynamic estimator and will not hit target
accurately. Run the identical graph twice, reading measured values from pass 1 into pass 2.

**Pass 1 — measure**

```bash
ffmpeg -hide_banner -i narration.wav -i music.wav -filter_complex "
[0:a]aformat=sample_fmts=fltp:channel_layouts=mono:sample_rates=48000,
     highpass=f=75:p=2:width_type=q:width=0.707,
     rubberband=pitch=0.917:formant=preserved:pitchq=quality:transients=smooth:detector=soft:phase=independent:window=standard:smoothing=off:channels=together,
     equalizer=f=240:width_type=q:width=1.2:g=-3,
     equalizer=f=450:width_type=q:width=1.5:g=-2,
     equalizer=f=950:width_type=q:width=2.5:g=-2.5,
     bass=f=115:width_type=q:width=0.7:g=2.5:p=2,
     equalizer=f=3100:width_type=q:width=0.9:g=2.5,
     treble=f=9000:width_type=q:width=0.7:g=1.5:p=2,
     acompressor=threshold=-20dB:ratio=2.5:attack=15:release=220:knee=4:makeup=1.6:detection=rms,
     deesser=i=0.12:m=0.4:f=0.6:s=o,
     aecho=in_gain=0.92:out_gain=0.07:delays=23|37:decays=0.11|0.07,
     asplit=2[v_mix][v_key];
[1:a]aformat=sample_fmts=fltp:channel_layouts=mono:sample_rates=48000,
     highpass=f=60:p=2,
     equalizer=f=2500:width_type=q:width=1.0:g=-3,
     volume=-11dB[bed];
[bed][v_key]sidechaincompress=threshold=0.01:ratio=10:attack=20:release=350:makeup=1:knee=2.83:detection=rms[bed_duck];
[v_mix][bed_duck]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,
     alimiter=limit=0.9:attack=5:release=60:asc=1,
     loudnorm=I=-14:TP=-1.5:LRA=7:print_format=json
" -map 0:a -f null - 2>&1 | tail -14
```

**Pass 2 — render.** Identical graph; replace the final filter with
`loudnorm=I=-14:TP=-1.5:LRA=7:linear=true:measured_I=<input_i>:measured_TP=<input_tp>:measured_LRA=<input_lra>:measured_thresh=<input_thresh>:offset=<target_offset>[out]`
then `-map "[out]" -ar 48000 -c:a pcm_s24le master.wav`.

### What each stage is for

| Stage | Why |
|---|---|
| `highpass=75` | Removes sub-speech rumble that eats headroom and muddies the bed mix. |
| `rubberband pitch=0.917` | **−1.5 semitones, formants preserved** — this is where depth comes from. Controllable and reversible, unlike a blend. 0.917 = 2^(−1.5/12). Stay within −1 to −2 semitones; beyond that artefacts accumulate over long passages. Prefer this over `asetrate`+`atempo`, which shifts formants and produces the chipmunk/giant effect. |
| Cuts at 240 / 450 / 950 Hz | Mud and boxiness. Cutting here does more for perceived depth than boosting bass. |
| `bass=115 +2.5` | Chest weight, below the mud region. |
| `equalizer 3100 +2.5` | Presence — consonant intelligibility, which matters more once you have pitched down. |
| `treble 9000 +1.5` | Air. Keep gentle; TTS has little genuine HF content. |
| `acompressor 2.5:1 @ −20dB` | Evens level. Slow-ish 15 ms attack keeps consonant transients; 220 ms release avoids pumping. |
| `deesser` | Pitching down accentuates sibilance; this puts it back. |
| `aecho` at 7% wet | Very light room tone. TTS is unnaturally dry; a touch of early reflection reads as "recorded in a place" rather than "generated". |
| `sidechaincompress` | Ducks the bed off the narration key. |
| `volume=-11dB` on bed | With the sidechain this lands the duck near **12–15 dB**, against the current 19.5 dB. Tune this one number by measurement, not by ear. |
| `alimiter limit=0.9` | Catches inter-sample peaks before loudnorm. |
| `loudnorm I=-14 TP=-1.5 LRA=7` | −14 LUFS is the YouTube-normalisation-friendly target; **LRA 7 against the current 2.3** gives the delivery some range instead of a flat wall. |

**Order matters:** pitch shift before EQ (so the EQ acts on the final spectrum), compression
after EQ, de-ess after compression, loudness last.

---

## 6. Gates to add

Extends `docs/qa-hardening-brief.md`.

| Gate | Threshold |
|---|---|
| `tts-phoneme-coverage` | zero chunks where a glossary name resolved to empty phonemes |
| `tts-lexicon-valid` | every lexicon entry passes the `US_VOCAB` check |
| `tts-chunk-band` | 95% of chunks between 120 and 200 phonemes |
| `tts-speed-range` | `kokoro_speed` within 0.90–1.05 |
| `audio-duck-depth` | narration p75 minus quiet-window floor within 12–15 dB |
| `audio-lra` | LRA between 5 and 9 LU |
| `audio-true-peak` | ≤ −1.0 dBTP |

## 7. Order of work

1. Run the §0 silent-deletion test. It may already be costing you every character name.
2. Switch `am_adam` → `am_michael`. One config line.
3. Split `tts_text` from `subtitle_text`, add `pronunciation` to the glossary.
4. Build the lexicon for the two existing series, with the validator.
5. Measure F0 across the male voices; revisit the voice choice on numbers.
6. Tighten the script, then drop `speed` into 0.92–1.00 and re-measure the WPM curve.
7. Enforce the chunk-length band.
8. Land the mastering chain, then tune the bed `volume` until duck depth measures 12–15 dB.
