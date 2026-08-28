# CORRECTION 01 to `audio-quality-spec.md`

**Issued 2026-08-28, after the §0.6 listening gate. Read before implementing anything from
§0.4 of `audio-quality-spec.md`.**

This document supersedes the lexicon in `audio-quality-spec.md` §0.4. If your copy of that
file already contains a section numbered **§0.4b**, you have the updated version and this
document is a summary of the same change. If it does not, your copy is stale and **the
27-entry lexicon in it must not be used**.

---

## 1. What happened

The original spec proposed a 27-entry pronunciation lexicon to fix Korean names. The A/B
render was produced and the user listened. **The user judged BEFORE (espeak, no lexicon)
to sound better than AFTER (lexicon applied).** The proposal is rejected.

The rest of `audio-quality-spec.md` — the `unk=''` mechanism, the two failure paths, voice
selection, speed, chunking, mastering — is unaffected and still stands. **Only the lexicon
contents and the policy behind them change.**

## 2. Measured diagnosis

10 ms RMS envelope over both renders of the same sentence:

| | before (espeak) | after (v1 lexicon) |
|---|---|---|
| duration | 7.22 s | 6.90 s |
| syllable-energy peaks | 38 | **46** |
| articulation rate | 5.3 /s | **6.7 /s** |
| internal pauses ≥60 ms | 4 | **5**, two of them 90 ms apart mid-word |

26% more energy peaks in a shorter duration: the TTS was **over-articulating**.

Two root causes, both errors in the original spec:

1. **Every per-syllable entry carried its own primary stress**, so concatenation produced
   two stresses inside one name — `jˌʌˈun` (Yeo-un), `ʤˈʌŋwˌu` (Jung-woo). English TTS
   renders that as two stressed units with a break between them.
2. **Every vowel was written full, never reduced.** Phonetically faithful Korean, unnatural
   English. English narration reduces unstressed vowels to schwa.

**The objective was wrong.** The original optimised for phonetic accuracy. The correct
objective is *recognisably the right name, carried on natural English prosody* — and espeak
already supplies the prosody. Accuracy that costs fluency is a net loss.

## 3. Corrected policy

**Override only where espeak changes a consonant, inserts a glide, or splits a syllable —
i.e. where the name's identity breaks. Leave every vowel approximation alone.**

Espeak's output on this repo's roster, classified:

**Leave alone — recognisable, and they carry the prosody the user preferred**
`Cheon`→`ʧən` · `Chung`→`ʧˈʌŋ` · `Gong`→`ɡˈɔŋ` · `Sung`→`sˈʌŋ` · `Yul`→`jˈʌl` ·
`Cha`→`ʧˈɑ` · `Jinwoo`→`ʤˈɪnwu` · `Jin-Woo`→`ʤˈɪnwˌu` · `Jun-Ho`→`ʤˈʌnhˌO` ·
`Hae-In`→`hˈAˌɪn` · `Shimuk`→`ʃˈɪmʌk` · `Carthenon`→`kˈɑɹθɛnən` ·
`Athanasia`→`ˌæθənˈAʒə` · `Baek`→`bˈik` · `Yeon`→`jˈOn` · `Yeo-un`→`jˈOˈʌn`

`Baek`→"beek" and `Yeon`→"YOHN" are wrong but recognisable. **They stay.** Overriding them
costs prosody and buys nothing an audience notices.

**Override — identity is broken**
`Jung`→`jˈʊŋ` (J→Y) · `Chi`→`kˈI` (Ch→K) · `Myung`→`mˈIʌŋ` (split) ·
`Si-eun`→`sˈijˈun` (Y glide) · `Jae-hwan`→`jˈiˈAʧwˈæn` (destroyed) ·
`Murim`→`mjˈʊɹɹɪm` (j glide) · `Mu`→`mjˌu` (j glide) · `Deok`→`diˈɑk` (split)

## 4. The replacement lexicon — 8 entries, not 27

```python
US_VOCAB = 'AIOWYbdfhijklmnpstuvwzæðŋɑɔəɛɜɡɪɹɾʃʊʌʒʤʧˈˌθᵊᵻʔ'

# 8/8 validated. Preserves espeak's vowels and stress; changes only broken consonants.
MIN_LEX = {
 "Jung":     "ʤˈʊŋ",       # espeak jˈʊŋ        J -> Y
 "Chi-Yul":  "ʧˈijʌl",     # espeak kˈIjˈʌl     Ch -> K
 "Myung":    "mjˈʌŋ",      # espeak mˈIʌŋ       split into two syllables
 "Si-eun":   "sˈiʌn",      # espeak sˈijˈun     inserted Y glide
 "Jae-hwan": "ʤˈɛhwɑn",    # espeak jˈiˈAʧwˈæn  destroyed
 "Murim":    "mˈuɹɪm",     # espeak mjˈʊɹɹɪm    inserted j glide
 "Mu":       "mˈu",        # espeak mjˌu        inserted j glide
 "Deok-Gu":  "dˈʌkɡu",     # espeak diˈɑkɡˈu    split into three syllables
}

for w, ps in MIN_LEX.items():
    bad = [c for c in ps if c not in US_VOCAB]
    assert not bad, f"{w}: illegal phonemes {bad}"
    for v in {w, w.lower(), w.upper(), w.capitalize()}:
        pipeline.g2p.lexicon.golds[v] = ps
```

Verified effect — everything not listed is left untouched:

```
Min Jung-woo   espeak 'mˈɪn jˈʊŋwˈu'   ->  'mˈɪn ʤˈʊŋwˌu'
Chung Myung    espeak 'ʧˈʌŋ mˈIʌŋ'     ->  'ʧˈʌŋ mjˈʌŋ'
Yeon Si-eun    espeak 'jˈOn sˈijˈun'   ->  'jˈOn sˈiʌn'
Jae-hwan       espeak 'jˈiˈAʧwˈæn'     ->  'ʤˈɛhwɑn'
Cheon Yeo-un   espeak 'ʧən jˈOˈʌn'     ->  unchanged
Sung Jin-Woo   espeak 'sˈʌŋ ʤˈɪnwˌu'   ->  unchanged
Baek           espeak 'bˈik'           ->  unchanged
```

## 5. Mechanical finding — hyphenated names need whole-name keys

Verified: **a per-syllable key does not fire inside a hyphenated token.** `"Chi"` and
`"Deok"` had no effect on `Chi-Yul` and `Deok-Gu`; misaki looks up the whole hyphenated
string. That is why those two entries above are whole-name.

`Jung` works per-syllable because misaki *does* split `Jung-woo`. **Behaviour differs per
name — test both forms for every entry you add.**

## 6. If you have already implemented the old lexicon

1. Remove the 27-entry dictionary entirely. Do not try to patch it — the stress and
   full-vowel problems are in nearly every entry.
2. Replace with `MIN_LEX` above.
3. Re-run the A/B render (`audio-quality-spec.md` §0.3 Script 3) and have the user listen
   again. **Accept only if after ≥ before on the user's ear.**
4. Re-measure the envelope: articulation rate should stay near the espeak baseline of
   ~5.3 /s. A rise toward 6.7 /s means over-articulation has returned and an entry is
   carrying too much stress.

## 7. Rules for any future lexicon entry

- **One primary stress per name, maximum. Never two.**
- **Copy espeak's vowels unless they break identity.** Do not "correct" them.
- **Prefer schwa in non-initial syllables.** Full vowels read as foreign and choppy.
- **Change the minimum number of phonemes that fixes the name.**
- **Test hyphenated and unhyphenated forms** — lookup behaviour differs.
- **Every new entry gets an A/B listen before it ships.** The phoneme string being "more
  correct" is not evidence that the audio is better. That assumption is what failed here.
