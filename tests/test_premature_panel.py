"""The max_shot split borrowed panels that later sentences had already claimed.

Reported from watching Solo Leveling: a close-up of a hunter's leg appeared once before
the narration reached it, then again at the line that describes it. Reproduced from the
shipped artifacts — p0134_02 shown at 605.2 s while its sentence speaks at 627.3 s
(22.1 s early), p0136_01 16.4 s early, and two more in Frozen Player.

Cause: the split pass built its `used` set from `plan` (beats already emitted) plus the
current beat. `plan[beat_id]` is written at the END of each iteration, so every LATER
beat was invisible to it — even though `flat` had already resolved them — and "the
nearest unused panel" happily borrowed one a later sentence owned.

The fixture below is the smallest shape that fires it: the over-long panel is ADJACENT
to a panel a later beat claims, and the only genuinely-free panel is farther away. With
a free panel nearer than the claimed one the old code picks the free one by luck, which
is why a casually-built fixture passes on both versions and proves nothing.

At HEAD this fixture produced beat1=[p01, p02], beat2=[p03] — note the second half of
the damage: the borrow displaced sentence 3 off the panel it had claimed.

No gate caught this in the render. `no-invisible-cuts` only fuses ADJACENT entries, so a
non-adjacent repeat is invisible to it, and `panel-utilisation` counts distinct panels
and silently reports a lower number.
"""

from __future__ import annotations

import pytest

from manhwa2vid.script.match import plan_shots_with_sentences

ORDER = ["p01", "p02", "p03"]


@pytest.fixture
def plan():
    """Beat 1 holds p01 for 18 s (over a 10 s cap) across two sentences, so it must
    split. p02 sits next to p01 but belongs to sentence 3, over in beat 2. p03 is free
    but farther away."""
    shotlist = {"sentences": [
        {"number": 1, "beat_id": 1, "text": "One.", "panels": ["p01"]},
        {"number": 2, "beat_id": 1, "text": "Two.", "panels": []},
        {"number": 3, "beat_id": 2, "text": "Three.", "panels": ["p02"]},
    ]}
    segments = {
        1: [{"text": "One.", "seconds": 9.0}, {"text": "Two.", "seconds": 9.0}],
        2: [{"text": "Three.", "seconds": 3.0}],
    }
    out = plan_shots_with_sentences(
        shotlist, segments, panel_order=ORDER, max_shot=10.0, floor=1.0
    )
    assert out is not None
    return out


def _flat(plan):
    return [row for beat in sorted(plan) for row in plan[beat]]


def test_the_split_does_not_borrow_a_panel_a_later_sentence_claims(plan):
    shown_before = [pid for pid, _s, _n in plan[1]]
    assert "p02" not in shown_before, (
        f"beat 1 showed p02, which sentence 3 claims in beat 2: {shown_before}"
    )


def test_the_claiming_sentence_keeps_its_own_panel(plan):
    """The follow-on half of the defect: the borrow displaced the rightful owner."""
    assert [pid for pid, _s, _n in plan[2]] == ["p02"]


def test_no_panel_is_shown_before_the_sentence_that_claims_it(plan):
    """The general invariant, stated as the render experiences it."""
    speaks_at = {"p01": 0.0, "p02": 18.0}
    t = 0.0
    for pid, sec, _nums in _flat(plan):
        if pid in speaks_at:
            assert t >= speaks_at[pid] - 1.0, f"{pid} at {t:.1f}s, claimed at {speaks_at[pid]:.1f}s"
        t += sec


def test_a_claimed_panel_is_never_shown_twice(plan):
    shown = [pid for pid, _s, _n in _flat(plan)]
    assert len(shown) == len(set(shown)), f"repeat in {shown}"


def test_the_split_still_happens_using_the_genuinely_free_panel(plan):
    """The fix must not disable the split — it exists so an 18 s hold becomes two shots,
    and 28-41% of story panels never reach the screen, so spares are available."""
    assert len(plan[1]) == 2, f"the over-long shot was not split: {plan[1]}"
    assert plan[1][1][0] == "p03", "the free panel farther away was not used"


def test_seconds_are_preserved_by_the_split(plan):
    """Audio/video lock: the split moves seconds between shots, never creates them."""
    assert abs(sum(sec for _p, sec, _n in _flat(plan)) - 21.0) < 0.01
