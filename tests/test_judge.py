"""Pairwise judge: comparative decisions where absolute ones were decided by confounds."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from manhwa2vid.models import Panel, PanelBBox


@pytest.fixture()
def panels(tmp_path):
    (tmp_path / "panels").mkdir()
    out = []
    for i in range(1, 4):
        rel = f"panels/p000{i}_01.png"
        Image.new("RGB", (80, 120), "white").save(tmp_path / rel)
        out.append(Panel(id=f"p000{i}_01", page_num=i,
                         bbox=PanelBBox(x=0, y=0, width=80, height=120), image_path=rel))
    return tmp_path, out


class _Judge:
    """Records prompts and answers by a rule over the candidate text."""

    def __init__(self, prefer: str | None = None, verdicts: list[str] | None = None):
        self.prefer, self.verdicts, self.calls = prefer, verdicts or [], []

    def describe_panels(self, images, prompt):
        import json
        self.calls.append(prompt)
        if self.verdicts:
            return json.dumps({"winner": self.verdicts[len(self.calls) - 1], "why": "x"})
        # position-independent: pick whichever slot holds the preferred text
        first_block = prompt.split("Candidate A:")[1].split("Candidate B:")[0]
        return json.dumps({"winner": "A" if self.prefer in first_block else "B", "why": "x"})


def test_judge_is_position_independent(panels):
    """A real preference must survive the swap — that is the whole point of running it
    twice."""
    from manhwa2vid.script.judge import pick_better

    root, ps = panels
    llm = _Judge(prefer="GOOD")
    kept, why = pick_better(ps, root, {}, "GOOD text", "BAD text", llm=llm)
    assert kept == "GOOD text"
    assert len(llm.calls) == 2  # both orderings asked

    kept, _ = pick_better(ps, root, {}, "BAD text", "GOOD text", llm=_Judge(prefer="GOOD"))
    assert kept == "GOOD text"


def test_position_bias_alone_decides_nothing(panels):
    """A judge that always says 'A' has expressed no preference; the caller's default
    wins rather than whichever candidate happened to be printed first."""
    from manhwa2vid.script.judge import pick_better

    root, ps = panels
    kept, why = pick_better(ps, root, {}, "first", "second",
                            default="a", llm=_Judge(verdicts=["A", "A"]))
    assert kept == "first" and "undecided" in why

    kept, why = pick_better(ps, root, {}, "first", "second",
                            default="b", llm=_Judge(verdicts=["A", "A"]))
    assert kept == "second" and "undecided" in why


def test_judge_failure_and_empty_candidates_fall_back(panels):
    from manhwa2vid.script.judge import pick_better

    root, ps = panels

    class Broken:
        def describe_panels(self, images, prompt):
            raise RuntimeError("no service")

    kept, _ = pick_better(ps, root, {}, "narration", "outline", default="a", llm=Broken())
    assert kept == "narration"

    kept, why = pick_better(ps, root, {}, "", "outline", llm=_Judge(prefer="x"))
    assert kept == "outline" and "empty" in why


def test_judge_can_be_disabled_and_needs_panels(panels):
    from manhwa2vid.script.judge import pick_better

    root, ps = panels
    off = {"script": {"pairwise_judge": False}}
    kept, _ = pick_better(ps, root, off, "a", "b", default="a", llm=_Judge(prefer="b"))
    assert kept == "a"

    kept, _ = pick_better([], root, {}, "a", "b", default="a", llm=_Judge(prefer="b"))
    assert kept == "a"


def test_judge_prompt_avoids_mock_branch_collisions():
    """A judge prompt containing 'fact-check' would be answered by the verifier branch
    with severity:none and silently always pass."""
    from manhwa2vid.script.judge import _JUDGE_PROMPT

    low = _JUDGE_PROMPT.lower()
    for hazard in ("fact-check", "panel sample", "annotate only these",
                   "beat-by-beat", "plot_beat", "rewrite this recap beat"):
        assert hazard not in low
    assert "length is not a criterion" in low  # verbosity-bias guard
