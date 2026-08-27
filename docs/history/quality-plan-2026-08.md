# Script quality plan — closing the gap to the reference

> **Superseded in part (2026-08-18).** Current architecture lives in
> [`architecture.md`](../architecture.md) — this file is kept as the record of what was
> diagnosed and why. One prescription here has since been **reversed**: Fix A1 called for
> chunked narration with carried state, and chunking turned out to CAUSE the cross-beat
> repetition it was meant to contain, because no single call ever saw the whole chapter.
> Narration is now one call for the entire script (`script.narration_chunk_size: 0`). The
> beat-conservation gate from Fix A2 remains, and is what makes the single call safe.
>
> **Status (2026-08-15): implemented.** All five root-cause fixes and their gates are live;
> `tests/test_qa_gates.py` holds one regression fixture per critique bug (73 tests green).
> Two deviations from the plan as written: character intros key on bible tier
> (main/supporting get name + intro clause) rather than appearance count, since target
> videos are long-form; and the vision model is `qwen/qwen3.6-27b` — the planned
> llama-4-scout is not available on the current Groq key.

Every defect found in the chapter-1 critique traces to one of five root causes. This plan fixes
by root cause, not by symptom, and pairs every fix with a **gate** — a deterministic check that
fails loudly so the pipeline can never silently degrade again. Issue numbers refer to the
critique (1–20).

Guiding target: the measured reference profile in `reference/style_profile.md` plus the
introduction/anchoring stats measured from the same transcript:

| Reference behavior | Measured value |
|---|---|
| MC anchored by NAME, then pronouns | one anchor per ~80 words; 6.4 pronouns per anchor |
| Anchor token | the character's name (941×), not "the protagonist" |
| New characters | bare name is common, BUT re-anchored every ~80 words for 5 hours |
| Dialogue | reported speech, a says/asks/tells every ~32 words |
| Register | concrete verbs, present tense, zero art-description |

---

## Root cause A — The narration pass is a single unchecked LLM call
**Causes issues 1, 2, 3 (beat loss → panel dumping → no ending).**

The outline's 18 beats go into ONE completion; whatever subset comes back is accepted
(`generate.py:430`). Beats 3–9 vanished and `_attach_missing_panels_to_beats` buried the
evidence by re-homing their 16 panels.

**Fix A1 — chunked narration with carried state.** Generate narration in chunks of ~5 beats.
Each chunk's prompt carries: the running story-so-far (from already-written chunks), the
introduction ledger (who has been named so far — see C2), and only that chunk's evidence.
Smaller outputs stop truncation/merging; carried state fixes continuity across chunks.

**Fix A2 — beat conservation gate (the most important check in this plan).** After narration:
`set(outline.beat_ids) == set(script.beat_ids)`, every beat's `panel_ids` identical to its
outline beat, non-empty narration on each. A missing beat triggers a single-beat retry (one
beat, its evidence, nothing else); still missing after 2 tries → **hard stage failure**, never
silent re-homing. `_attach_missing_panels_to_beats` becomes a last-resort that must print which
beats/panels it touched and is itself gated (>10% of panels re-homed = failure).

**Fix A3 — mandatory closer beat.** The outline must end with a beat flagged `closer`, written
from `synopsis.open_threads` — the next-chapter hook. Gate: last beat exists, is flagged, and
its narration contains a forward-looking clause. (Issue 3, 20 partially — the closer is also
where one sentence of world-stakes lands naturally.)

---

## Root cause B — Character identity is not referentially closed
**Causes issues 4, 5, 6, 7, 12 (duplicate MC, self-conversations, wrong anchor tokens).**

`char_man_with_green_backpack` appears in cast attribution but **does not exist in the bible**.
Descriptor-derived IDs leak from scene cards into attribution without passing through
`resolve_character_ref`, so the MC exists as two people and the script has him decline his own
offer.

**Fix B1 — referential integrity gate.** After the cast stage: every `ref` in
`cast_attribution.json` and every `character_ids` entry downstream must exist in the bible and
not be `merged_into`-redirected. Dangling ID → run it through `resolve_character_ref`
(the "green backpack" signal already maps to the MC); unresolvable → fail the stage with the ID
and the panels that use it. This single gate makes issue 4 structurally impossible.

**Fix B2 — one-identity-per-panel rule.** `_normalize_mc_attribution` already collapses MC
duplicates *within* a card; extend the same collapse to descriptor variants of ANY bible
character (`char_guy_with_green_jacket` vs `char_guy_in_green_jacket_and_blue_jeans`), using
`profiles_are_same_person`. Gate: no two people in one panel may resolve to the same profile.

**Fix B3 — anchor policy rewritten to match the measurement.** Replace the current
`mc_labels` rotation ("MC", "the protagonist", "our guy") with the reference's actual pattern:
- anchor = the character's **name**; re-anchor roughly every 70–90 words or on scene change;
- between anchors, pronouns only (target ≥4 pronouns per anchor);
- "MC" is banned from narration text entirely (it is an internal ID, issue 7);
- "the protagonist" allowed at most once per chapter (it currently appears 10× in 351 words).
Enforced in the prompt AND in lint: anchor-density and pronoun-ratio checks with numeric
thresholds taken from `style_profile.md`.

**Fix B4 — descriptor quarantine.** Narration may never use a descriptor phrase ("the man with
the green backpack") for a character who has a canonical name in the bible. Lint: for each
name/descriptor n-gram in narration, look it up against bible descriptors; a hit on a *named*
profile is a violation (issue 5's exact failure).

---

## Root cause C — The vision layer invents, and nothing downstream doubts it
**Causes issues 9, 10, 11 (boast misattribution, inverted speaker, coffee-from-a-prop).**

Scene cards are generated with `ocr.enabled: false` — the VLM reads speech bubbles from a
768px-max image and *asserts* speakers. The card for `p0024_01` names Sung Jin-Woo as speaker
in a panel he is not in; narration then paraphrased the card faithfully. Garbage in, fluent
garbage out.

**Fix C1 — separate seeing from inferring.** Split the scene prompt into:
1. *transcribe*: verbatim bubble text + who is visible (appearance only, no names);
2. *infer*: map bubbles to visible people, THEN to bible identities.
A speaker may only be a person listed as visible in that panel. Gate: `speakers ⊆ people` per
card (today they don't even share a vocabulary — speakers are raw strings, people are refs).

**Fix C2 — enable OCR as ground truth.** PaddleOCR is already installed in this venv; flip
`ocr.enabled: true`. Where OCR text exists, the VLM's transcription must overlap it (token
overlap threshold); a card whose dialogue_summary contains content words absent from both OCR
and transcription is flagged `ungrounded` and its dialogue claims are stripped before script
stages see it. This is what kills the barista transaction built from a coffee cup (issue 11).

**Fix C3 — presence gate for ALL named cast, not just the MC.** `lint_mc_attribution` already
checks the protagonist; generalize: any bible name in a beat's narration whose profile is not
in that beat's panel attribution = violation (issues 9, 10). The critique's worst error — the
weakest hunter "boasting about being highest ranked" — fails this gate at two levels once C1
fixes the card and B1 fixes the attribution.

**Fix C4 — de-hardcode grounding keywords.** `GROUNDING_KEYWORDS` bakes coffee/food-truck/
healer into the code (and primed the coffee fixation). Build the keyword set per-chapter from
OCR + scene-card nouns instead; keep the mechanism, drop the Solo-Leveling constants. (Also
required anyway for Frozen Player.)

---

## Root cause D — The script paraphrases cards instead of telling a story
**Causes issues 8, 13, 14, 15, 16, 17, 18, 19, 20 (register, intros, art-description,
contradictions, verbatim dialogue, leak, hook dupe, no world-building).**

**Fix D1 — introductions via a ledger, sized to the recap.** Maintain an introduction ledger
across narration chunks. Policy tuned to short recaps (the reference can afford bare names
because it re-anchors for 5 hours; a 2-minute recap cannot):
- a character is *name-worthy* only if they appear in ≥3 beats or are flagged supporting+ in
  the bible; otherwise narration uses a role phrase and never spends a name (fixes the
  Kim Sang-shik-named-once-then-credits problem, issue 8);
- first use of a name-worthy character = name + one appositive clause from the bible
  (`role`/`visual`: "Lee Joo-hee, the party's healer") — the intro the user asked for;
- second use onward = name or pronoun, never the appositive again.
Gate: every name in narration is either in the ledger (introduced) or a violation; every
introduced character has ≥2 subsequent references or the intro is demoted to a role phrase.

**Fix D2 — register lint, hard list.** Ban in narration (regex, extends the existing hedge
lint): expresses/converses/interacts/discusses/mentions/responds/reacts as dialogue verbs;
"speech bubble", "the viewer", "panel", "the scene"; "a man/someone/two people/a group" when
the attribution for those panels resolves the person to a profile (issue 15 — anonymous agents
are only legal for genuinely unresolved people). Rewrite loop already exists; feed it these.

**Fix D3 — reported-speech transform.** The prompt requires quoting-to-reported conversion
("asks if", "tells him that") and forbids quotation marks in narration entirely. Lint: any
`'` / `"` quoted span >3 words = violation (issue 17). This is also the lever that closes the
dialogue-verb gap (17.1/1k → target ≥25/1k).

**Fix D4 — beat self-consistency.** Cheap NLI-style check per beat: extract negation pairs
("hadn't brought a healer" / "bothered to bring a healer") by scanning for the same content
noun under opposite polarity within one beat; violation → rewrite with the contradiction named
(issue 16).

**Fix D5 — hook/beat-1 dedup + leak scan.** Token-overlap between hook and beat 1 >60% =
rewrite beat 1 (issue 19). Scan narration for prompt-instruction phrases ("referred to as",
"the protagonist id", "beat_id") — the instruction-leak class (issue 18).

**Fix D6 — first-use world terms.** From the glossary's `terms` dict, the first beat using a
term (gate, rank, portal) gets a ≤6-word gloss folded into the sentence; later uses bare
(issue 20). Ledger-tracked like character intros.

---

## Root cause E — Nothing measures the output, so drift is invisible
**The meta-issue: every failure above shipped without a single warning.**

**Fix E1 — stage QA reports.** Every stage writes `qa.<stage>.json` (counts, gate results,
violations). `manhwa2vid run` prints a one-line verdict per stage; `manhwa2vid check --project`
re-runs all gates read-only. A failed gate blocks the next stage unless `--force-past-qa` is
given explicitly.

**Fix E2 — style scorecard vs the reference.** Promote the ad-hoc measurements into
`tools/script_report.py` (never built), which would have run after the script stage: words/beat, sentence
length, dialogue-verbs/1k, first-person/1k, slang/1k, anchor cadence, pronouns-per-anchor,
anonymous-agent count, register-verb count, art-description count — each with a target band
from `style_profile.md` and a PASS/WARN/FAIL. The scorecard is the definition of "close to the
reference"; we tune until it's green instead of arguing taste.

**Fix E3 — frame-alignment audit (sampled, adversarial).** After script: for each beat (or a
sample on long chapters), send the beat's panels + its narration back to the VLM with one
question — "list narration claims NOT supported by these images" — using a *different* prompt
persona than generation (a verifier, not a co-author). Claims flagged by the verifier AND
unsupported by OCR are violations. This is the check that would have caught the boast, the
barista, and the crowd-portal beat before render.

**Fix E4 — regression fixtures from this critique.** Each observed bug becomes a test:
outline→narration beat-drop (A2), dangling char_id (B1), speaker-not-in-people (C1),
descriptor-for-named-character (B4), MC-label spoken aloud (B3), quoted-span (D3),
hook-dupe (D5). The mock LLM gets branches that reproduce the bad outputs so gates are
exercised in CI.

---

## Order of work

| Step | Fixes | Why this order |
|---|---|---|
| 1 | A2, B1, E1 | The two integrity gates + reporting skeleton. Cheap, deterministic, stop the worst failures TODAY. |
| 2 | A1, A3 | Chunked narration with state; closer beat. Biggest single quality jump. |
| 3 | C1, C2, C3 | Vision grounding. Requires re-running OCR+scene stages (~cheap on Groq). |
| 4 | B2, B3, B4, D1–D6 | Anchor policy, intro ledger, register — the craft layer, now standing on reliable data. |
| 5 | E2, E3, E4, C4 | Scorecard, adversarial audit, regression tests, de-hardcoding. |

Steps 1–2 are a day of work and would have prevented issues 1–7 and 18–19 outright. The craft
layer (step 4) is where the output starts *sounding* like the reference; the scorecard (E2) is
how we prove it rather than assert it.

## What this plan deliberately does not do

- No new models, no fine-tuning — the current stack produced fluent text; it was fed bad data
  and never checked.
- No attempt to match the reference's 237 WPM by force — pace follows from denser scripts and
  the chosen voice; the scorecard tracks it but no gate enforces it.
- Chapter-1-only content (Solo Leveling signals, coffee keywords) gets *removed*, not improved
  (C4), since the target series is Return of the Frozen Player once pages exist.
