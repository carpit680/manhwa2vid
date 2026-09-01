"""The subtractive pass: appearance the frame shows, register the narration states.

Both rules were written from sentences that actually shipped (2026-08-31 measurement of
the three approved scripts), and both are deliberately narrow — this pass deletes, so a
false positive silently removes story. Every non-target below is a real sentence from
those same scripts that must survive.
"""

from __future__ import annotations

from manhwa2vid.script.trim import (
    apply_trim_pass,
    first_person_rate,
    meta_aside_rate,
)


# --- appearance ----------------------------------------------------------------------

def test_hair_and_clothing_go_but_the_injury_stays():
    """The shipped sentence carries BOTH an appearance dump and a story fact: he is
    already bandaged before the fight. Deleting the sentence would lose the fact, so
    the pass strips clauses rather than sentences."""
    text = ("He is a scruffy guy with black hair, dressed in a faded hoodie, "
            "sporting bandages on his face before the fighting even starts.")
    out, rec = apply_trim_pass(text)
    assert "black hair" not in out and "hoodie" not in out
    assert "sporting bandages on his face before the fighting even starts" in out
    assert rec["appearance"][0]["to"] == out


def test_a_role_survives_its_haircut():
    """"He is a veteran hunter." is information the viewer cannot see; the swept-back
    hair is information they are looking at."""
    out, _ = apply_trim_pass("He is a veteran hunter with swept-back hair.")
    assert out == "He is a veteran hunter."


def test_an_extra_identified_only_by_clothing_keeps_acting():
    out, _ = apply_trim_pass("A burly man in a sharp suit walks in.")
    assert out == "A burly man walks in."


def test_an_appearance_husk_is_dropped_whole():
    """Nothing left but the look — no role, no action, no fact."""
    text = "The party gathers at the gate. He is a scruffy guy with black hair."
    out, rec = apply_trim_pass(text)
    assert out == "The party gathers at the gate."
    assert any(a.get("rule") == "husk" for a in rec["appearance"])


# --- stated register -----------------------------------------------------------------

def test_the_narration_stops_explaining_its_own_joke():
    """All four shipped in Solo Leveling. Each one restates the sentence before it."""
    for line in ("It is a miserable life.", "It is an ironic title.",
                 "The money is terrible.", "This is an absolute nightmare."):
        text = f"He counts the coins in his palm. {line}"
        out, rec = apply_trim_pass(text)
        assert out == "He counts the coins in his palm.", line
        assert rec["stated_register"] == [line]


def test_plot_state_is_not_a_register_statement():
    """"It is too late." is what happens next, not a verdict on the story. Losing it
    would delete a beat — this is the false positive the rule is shaped to avoid."""
    text = "He reaches for the seal. It is too late."
    out, rec = apply_trim_pass(text)
    assert out == text and rec["stated_register"] == []


def test_a_fact_about_a_character_survives():
    text = "He is an E-Rank hunter. The raid wraps up quickly."
    out, rec = apply_trim_pass(text)
    assert out == text and rec["stated_register"] == []


def test_an_evaluative_word_inside_a_real_clause_is_left_alone():
    """The rule requires a dummy subject and a copula. A sentence that USES one of the
    evaluative words while doing story work is untouched."""
    text = "He admits the raid was brutal and asks the healer for help."
    out, _ = apply_trim_pass(text)
    assert out == text


# --- the outro and idempotency -------------------------------------------------------

def test_the_outro_paragraph_is_never_trimmed():
    outro = "It is a miserable life. Subscribe to see how it goes."
    out, _ = apply_trim_pass("He walks into the gate.\n\n" + outro)
    assert outro in out


def test_the_record_blocks_a_second_application(tmp_path):
    paths = {"debug": tmp_path}
    text = "He counts the coins. It is a miserable life."
    first, _ = apply_trim_pass(text, paths)
    second, rec = apply_trim_pass(first, paths)
    assert second == first and rec.get("skipped")


# --- persona counters ----------------------------------------------------------------

def test_first_person_ignores_quoted_character_dialogue():
    """"I'll kill you" is a character speaking, not the narrator breaking frame. The
    writer-narrator's first-person budget must not be spent by the cast."""
    quoted = 'She screams "I will kill you and end this nightmare" at him.'
    assert first_person_rate(quoted)["count"] == 0
    narrator = "I should explain the ranking system before this gets confusing."
    assert first_person_rate(narrator)["count"] == 1


def test_meta_asides_are_counted_not_deleted():
    """An aside is a sentence the writer built a paragraph around; the pass reports it
    for a human to cut rather than undoing the previous pass's work."""
    text = ("I should explain the ranking system here. The translation is rough. "
            "He walks into the gate.")
    out, rec = apply_trim_pass(text)
    assert out == text, "a meta-aside was deleted"
    assert meta_aside_rate(text)["count"] == 2
    assert any(f["rule"] == "meta-back-to-back" for f in rec["meta"])


def test_a_meta_aside_in_the_cold_open_is_flagged():
    text = "I want to talk about the art style first. He lies in a pool of blood."
    _, rec = apply_trim_pass(text)
    assert any(f["rule"] == "meta-in-hook" for f in rec["meta"])


def test_a_craft_remark_is_not_a_register_statement():
    """"The translation is rough." has the exact shape the register rule matches — dummy
    subject, copula, evaluative word — but it is the writer-narrator doing one of the
    five jobs it was asked to do. The register rule stands down on craft subjects; this
    collision was caught by the suite before it reached a script."""
    for craft in ("The translation is rough.", "The pacing here is terrible.",
                  "The art style is bleak."):
        text = f"He steps through the gate. {craft}"
        out, rec = apply_trim_pass(text)
        assert out == text, craft
        assert rec["stated_register"] == [], craft


def test_a_coordinate_adjective_does_not_hide_a_register_statement():
    """"It is a small, pathetic indignity." — the comma broke the filler match until the
    writer-narrator arms produced this exact sentence in a bake-off."""
    out, rec = apply_trim_pass("He asks for coffee. It is a small, pathetic indignity.")
    assert out == "He asks for coffee."
    assert rec["stated_register"] == ["It is a small, pathetic indignity."]


def test_compound_appearance_adjectives_go_with_the_article_fixed():
    """"an orange-haired healer" — appearance welded onto the noun, so the
    with/in/wearing pattern never sees it. Removing it must not strand "an"."""
    assert apply_trim_pass("She is an orange-haired healer.")[0] == "She is a healer."
    assert (apply_trim_pass("A black-haired man in a blue jacket waves.")[0]
            == "A man waves.")


def test_a_compound_that_can_carry_plot_survives():
    """-armed and -handed are deliberately excluded: losing an arm is a story event in
    this genre, not a description of what someone looks like."""
    text = "He is a one-armed veteran of the second floor."
    assert apply_trim_pass(text)[0] == text
