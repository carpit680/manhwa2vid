# Mamoru Manhwa — measured narration style

Derived from auto-captions of `drpDZ2HUGn8` ("Return of the Frozen Player" recap,
Mamoru Manhwa, 5h17m, 75,421 words). Statistics only — no transcript text is stored here.
Regenerate with `reference/profile_srt.py <file.srt>`.

## Measurements

| Metric | Value | Note |
|---|---|---|
| Speaking rate | **237 WPM** | stable: 5-min windows p10=228, median=237, max=255 |
| Sentence length | **12.8 words** mean (median 12, p10 6, p90 21) | short, declarative |
| Sentence cadence | **18.6/min → 3.2s of airtime each** | this is the visual beat too |
| Dialogue verbs (`says/asks/tells/replies`) | **31.3 per 1k words** | ~1 reported-speech verb every 32 words |
| Interiority (`thinks/realizes/notices`) | 6.4 per 1k | |
| First-person narrator (`I/me/my`) | **0.24 per 1k** | effectively zero asides in 5+ hours |
| Gen-Z slang (`ngl/lowkey/bro/no cap`) | **0.07 per 1k** (5 hits total) | effectively zero |
| Hype adjectives | 0.74 per 1k | sparing |
| Hedging (`maybe/seems/might`) | 2.16 per 1k | low |
| `the protagonist` | 4.4 per 1k | |
| `MC` | 3.3 per 1k | |
| Past-tense `-ed` tokens | 20.9 per 1k | narration is **present tense** |
| Opening hook | 87 words / ~5 sentences in first 20s | cold open, mid-scene |

## What this says about the voice

1. **Fast, plain, present-tense storytelling.** Not a hype announcer, not a Gen-Z bit. The
   energy comes from *rate* (237 WPM) and short sentences, not from slang or adjectives.
2. **Reported speech is the signature move.** A dialogue verb every ~32 words means the
   narrator constantly relays what people say and ask, rather than summarizing scenes
   abstractly. "The judge asks X, and he answers Y" is the dominant sentence shape.
3. **No FIRST PERSON — but a large persona.** 18 first-person tokens across 75k words:
   the narrator never becomes a character and never addresses the viewer. That is a rule
   about the pronoun "I", and reading it as "no personality" was an expensive mistake —
   it was encoded as `max_narrator_asides: 0`, `genz_level: none` and a
   "concrete events only" prompt rule, and the resulting narration read like a report.
   Measured over one two-chapter segment, the same narrator runs **8.2 evaluative asides,
   7.2 casual epithets for the hero and 2.0 similes per 1k words**, at **11.9-word mean
   sentences with 23% under seven words**. He interprets constantly ("scrolling headlines
   like a grandpa who just discovered the internet", "trading blows at Goku's speed"); he
   simply never says "I". Voice bands in `script/scorecard.py` now hold these as FLOORS,
   because too few is the failure mode.
4. **Label rotation over name repetition.** `the protagonist` and `MC` together appear ~7.7
   times per 1k words, alongside the character's actual name — confirming the rotation
   strategy already implemented in `characters/bible.py::naming_priority_rules`.
5. **Cold open.** No channel intro, no "in this video". It starts inside a scene.

## Mapping to pipeline config

| Finding | Knob | Was | Now |
|---|---|---|---|
| 237 WPM | `script.target_wpm` | 130 | 235 |
| No slang | `script.genz_level` | medium | none |
| No asides | `script.max_narrator_asides` | 1 | 0 |
| 3.2s sentence airtime | `video.min_panel_seconds` / `max_panel_seconds` | 2.5 / 10.0 | 2.0 / 5.0 |
| Narration must be delivered fast | `tts.pace_multiplier` | 0.85 | 1.15 |
| Reported speech + present tense | `script/prompts/recap.txt` | "do NOT read dialogue line-by-line" | narrate dialogue as reported speech, present tense |

`tts.pace_multiplier` is the weakest inference here: the reference channel's 237 WPM is
partly a sped-up edit, and Chatterbox's natural rate differs from that. Tune by ear against
a rendered preview rather than trusting the number.
