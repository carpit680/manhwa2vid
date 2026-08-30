"""The auditor was never shown what the read pass already knew.

Solo Leveling's opening line said "He is missing his right arm below the elbow" of
Sung Jin-Woo. The pages show both limbs, and `chapter_facts.json` — written by the read
pass from those same pages, before the narration existed — said plainly:

    "Song Chi-Yul loses his arm in the initial attack."

The auditor never saw that. `facts` reached `_undelivered_spine` only, so the LLM audit
call got the narration and the raw pages and had to re-derive from a drawing of a
bloodied figure whether the arm belonged to the protagonist. It did not catch it. (It
DID catch a sibling misattribution on the same script — "Mr. Kim holds up a glowing
magical core", actually Mr. Song — so the failure is coverage, not capability.)

Misattributing an action to the wrong character is this recap's most common factual
error and the read pass has already made those calls with more context.
"""

from __future__ import annotations

from manhwa2vid.script.audit import _facts_block

FACTS = {
    "plot_spine": [
        "Sung Jin-Woo is introduced as a heavily injured E-Rank hunter facing statues.",
        "Song Chi-Yul loses his arm in the initial attack.",
    ],
    "cast": [
        {"name": "Sung Jin-Woo", "aliases": ["The world's weakest"], "note": "protagonist"},
        {"name": "Song Chi-Yul", "aliases": ["Mr. Song"], "note": "C-Rank Hunter, party leader"},
    ],
    "key_dialogue": [
        {"page": "0002", "speaker": "Sung Jin-Woo", "line": "My name is Sung Jin-Woo."},
    ],
    "system_messages": ["ignored here"],
}


def test_the_arm_fact_reaches_the_prompt():
    block = _facts_block(FACTS)
    assert "Song Chi-Yul loses his arm" in block


def test_the_cast_is_included_so_who_is_who_is_checkable():
    block = _facts_block(FACTS)
    assert "Song Chi-Yul" in block and "Mr. Song" in block
    assert "Sung Jin-Woo" in block


def test_dicts_are_formatted_not_repr_ed():
    """`key_dialogue` and `cast` hold dicts. str()-ing them put Python repr — braces,
    quoted keys — into the prompt, which is what the first version did."""
    block = _facts_block(FACTS)
    assert "{" not in block and "'speaker'" not in block
    assert 'Sung Jin-Woo: "My name is Sung Jin-Woo."' in block


def test_the_right_keys_are_read():
    """`plot_spine`, not `spine` — the first version read a key that does not exist and
    silently produced a block with no events in it."""
    assert "loses his arm" not in _facts_block({"spine": ["Song Chi-Yul loses his arm."]})
    assert "loses his arm" in _facts_block({"plot_spine": ["Song Chi-Yul loses his arm."]})


def test_no_facts_means_no_block():
    """An older project without chapter_facts.json must audit exactly as before."""
    assert _facts_block(None) == ""
    assert _facts_block({}) == ""
    assert _facts_block({"system_messages": ["x"], "time_markers": ["y"]}) == ""


def test_the_block_is_bounded():
    big = {"plot_spine": [f"Event number {i} happens." for i in range(200)],
           "cast": [{"name": f"Person {i}"} for i in range(200)],
           "key_dialogue": [{"speaker": f"P{i}", "line": "x"} for i in range(200)]}
    block = _facts_block(big)
    assert block.count("\n- ") <= 62, "the facts would drown the pages in the prompt"
