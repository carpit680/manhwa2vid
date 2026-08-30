"""Shot-list construction: the deterministic half of sentence→panel matching.

The vision call decides WHICH panels depict a sentence; everything tested here decides
what that becomes on screen. Measured motivation: with panels apportioned by airtime
alone, 86% (Frozen Player) and 93% (Solo Leveling) of matchable sentences were showing a
panel that does not depict them.
"""

from __future__ import annotations

from manhwa2vid.script.match import filter_monotonic, plan_shots


# --- the monotonic filter -----------------------------------------------------------

def test_monotonic_filter_drops_backward_claims():
    """A model claim that runs against the story's forward motion is dropped, not
    negotiated with: sentences advance, so the panels they claim must advance too."""
    order = ["p1", "p2", "p3", "p4", "p5"]
    claims = [
        (1, "p1"),
        (2, "p2"),
        (3, "p1"),   # sentence 3 reaching BACK to panel 1 — contradiction
        (4, "p4"),
        (5, "p5"),
    ]
    kept = filter_monotonic(claims, order)
    assert (3, "p1") not in kept
    assert [c for c in kept] == [(1, "p1"), (2, "p2"), (4, "p4"), (5, "p5")]


def test_monotonic_filter_keeps_the_largest_consistent_set():
    """When claims conflict, keep the most that CAN be true together — a single early
    outlier must not cost us the whole chain behind it."""
    order = [f"p{i}" for i in range(1, 8)]
    claims = [(1, "p7"), (2, "p2"), (3, "p3"), (4, "p4"), (5, "p5")]
    kept = filter_monotonic(claims, order)
    assert len(kept) == 4 and (1, "p7") not in kept


def test_monotonic_filter_ignores_unknown_panels():
    assert filter_monotonic([(1, "ghost")], ["p1"]) == []
    assert filter_monotonic([], ["p1"]) == []


# --- planning: claims + measured seconds -> shots ------------------------------------

def _sl(*specs):
    return {"sentences": [
        {"number": i + 1, "beat_id": 1, "text": f"s{i+1}", "panels": list(p)}
        for i, p in enumerate(specs)
    ]}


def test_commentary_holds_the_previous_shot():
    """A sentence that depicts nothing extends the shot it is commenting on — the user's
    choice, and what Mamoru does (17% of his shots run over 6 seconds)."""
    plan = plan_shots(_sl(["p1"], [], ["p2"]),
                      {1: [{"seconds": 3.0}, {"seconds": 2.0}, {"seconds": 3.0}]}, floor=1.0)
    assert plan[1] == [("p1", 5.0), ("p2", 3.0)]


def test_leading_commentary_attaches_to_the_first_real_shot():
    """Nothing has been shown yet, so a leading aside cannot hold anything — its seconds
    ride the first panel that IS claimed rather than vanishing."""
    plan = plan_shots(_sl([], ["p9"]), {1: [{"seconds": 2.0}, {"seconds": 3.0}]}, floor=1.0)
    assert plan[1] == [("p9", 5.0)]


def test_multi_panel_sentence_splits_its_seconds():
    plan = plan_shots(_sl(["p1", "p2"]), {1: [{"seconds": 6.0}]}, floor=1.0)
    assert plan[1] == [("p1", 3.0), ("p2", 3.0)]


def test_repeated_panel_folds_instead_of_cutting_to_itself():
    plan = plan_shots(_sl(["p1"], ["p1"]), {1: [{"seconds": 2.0}, {"seconds": 2.0}]}, floor=1.0)
    assert plan[1] == [("p1", 4.0)]


def test_short_shot_merges_and_total_seconds_survive():
    """Under-floor shots merge rather than strobing, and the beat's audio length is
    preserved exactly — A/V lock is downstream of this."""
    plan = plan_shots(_sl(["p1"], ["p2"]), {1: [{"seconds": 3.0}, {"seconds": 0.4}]}, floor=1.0)
    assert plan[1] == [("p1", 3.4)]

    plan = plan_shots(_sl(["p1"], ["p2"]), {1: [{"seconds": 0.4}, {"seconds": 3.0}]}, floor=1.0)
    assert plan[1] == [("p2", 3.4)], "a short FIRST shot has no previous to merge into"


def test_mismatched_sidecar_refuses_to_guess():
    """Sentence identity is the contract. If the sidecar and the shot list disagree the
    planner returns None so the caller falls back, rather than pairing the wrong seconds
    with the wrong panel and silently desynchronising picture from sound."""
    assert plan_shots(_sl(["p1"], ["p2"]), {1: [{"seconds": 3.0}]}, floor=1.0) is None
    assert plan_shots(_sl(["p1"]), {}, floor=1.0) is None


def test_hold_carries_across_a_beat_boundary():
    """A beat opening on commentary holds what the previous beat left on screen."""
    shotlist = {"sentences": [
        {"number": 1, "beat_id": 1, "text": "a", "panels": ["p1"]},
        {"number": 2, "beat_id": 2, "text": "b", "panels": []},
        {"number": 3, "beat_id": 2, "text": "c", "panels": ["p2"]},
    ]}
    segs = {1: [{"seconds": 3.0}], 2: [{"seconds": 2.0}, {"seconds": 3.0}]}
    plan = plan_shots(shotlist, segs, floor=1.0)
    assert plan[1] == [("p1", 3.0)]
    assert plan[2] == [("p1", 2.0), ("p2", 3.0)], "beat 2 opens on the held panel"


def test_shot_plan_entries_carry_their_audio_file(tmp_path):
    """A shot-plan render came out completely SILENT and nothing failed.

    _mix_audio collects narration by reading `audio_file` off the timeline entries; the
    shot-plan branch built entries without it, so the list came back empty and _mix_audio
    treated that as "no narration" and copied the video straight through. Silence is the
    one defect that no gate looks for, so it is pinned here.
    """
    import wave

    from manhwa2vid.models import Panel, PanelBBox, ScriptBeat
    from manhwa2vid.video.timeline import build_timeline

    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    wav = audio_dir / "beat_001.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(b"\x00\x00" * 24000 * 4)   # 4 seconds

    panels = [
        Panel(id=f"p0001_{i:02d}", page_num=1,
              bbox=PanelBBox(x=0, y=0, width=10, height=10),
              image_path=f"panels/p0001_{i:02d}.png")
        for i in (1, 2)
    ]
    beats = [ScriptBeat(beat_id=1, panel_ids=[p.id for p in panels], narration="One. Two.")]
    timeline = build_timeline(
        beats, panels, audio_dir, {},
        shot_plan={1: [("p0001_01", 2.0), ("p0001_02", 2.0)]},
    )
    assert timeline.entries, "the shot plan must produce entries"
    assert all(e.audio_file for e in timeline.entries), "every entry needs its audio file"
    assert {e.audio_file for e in timeline.entries} == {"audio/beat_001.wav"}


# --- bounded fill + accent cuts (2026-08-26 revision) --------------------------------

def test_unmatched_run_walks_the_panels_between_anchors():
    """SL matched only 49% of sentences; holding made half the picture stand still.
    An unmatched run now walks the unclaimed panels BETWEEN its anchors, in reading
    order — bounded, so it can never jump to an unrelated image."""
    order = ["p1", "p2", "p3", "p4", "p5"]
    plan = plan_shots(
        _sl(["p1"], [], [], ["p5"]),
        {1: [{"seconds": 3.0}, {"seconds": 2.0}, {"seconds": 2.0}, {"seconds": 3.0}]},
        floor=1.0,
        panel_order=order,
    )
    shown = [pid for pid, _ in plan[1]]
    assert shown == ["p1", "p2", "p3", "p4", "p5"], shown
    assert abs(sum(sec for _, sec in plan[1]) - 10.0) < 1e-6, "A/V total preserved"


def test_fill_without_gap_panels_still_holds():
    """No panels between the anchors -> the old hold behaviour stands."""
    plan = plan_shots(
        _sl(["p1"], [], ["p2"]),
        {1: [{"seconds": 3.0}, {"seconds": 2.0}, {"seconds": 3.0}]},
        floor=1.0,
        panel_order=["p1", "p2"],
    )
    assert plan[1] == [("p1", 5.0), ("p2", 3.0)]


def test_fill_needs_both_anchors():
    """A trailing unmatched run has no right bound — it holds rather than wandering
    into panels the narration may never reach."""
    plan = plan_shots(
        _sl(["p1"], [], []),
        {1: [{"seconds": 3.0}, {"seconds": 2.0}, {"seconds": 2.0}]},
        floor=1.0,
        panel_order=["p1", "p2", "p3"],
    )
    assert plan[1] == [("p1", 7.0)]


def test_fill_subsamples_a_wide_gap_in_order():
    """More gap panels than the run's airtime can carry at the floor: subsample evenly,
    order preserved, each shot at least the floor."""
    order = [f"p{i}" for i in range(1, 13)]
    plan = plan_shots(
        _sl(["p1"], [], ["p12"]),
        {1: [{"seconds": 2.0}, {"seconds": 3.0}, {"seconds": 2.0}]},
        floor=1.0,
        panel_order=order,
    )
    shown = [pid for pid, _ in plan[1]]
    assert shown[0] == "p1" and shown[-1] == "p12"
    middle = shown[1:-1]
    assert 1 <= len(middle) <= 3, f"airtime caps the fill: {middle}"
    positions = [order.index(p) for p in shown]
    assert positions == sorted(positions), "reading order preserved"


def test_fill_skips_panels_claimed_elsewhere():
    """A panel matched to a LATER sentence is not stolen by the fill."""
    order = ["p1", "p2", "p3", "p4"]
    plan = plan_shots(
        _sl(["p1"], [], ["p3"], ["p4"]),
        {1: [{"seconds": 2.0}, {"seconds": 2.0}, {"seconds": 2.0}, {"seconds": 2.0}]},
        floor=1.0,
        panel_order=order,
    )
    shown = [pid for pid, _ in plan[1]]
    assert shown == ["p1", "p2", "p3", "p4"]


def test_accent_cut_survives_below_the_floor():
    """A multi-panel action sentence keeps its intra-sentence cuts below the 1.0s
    floor — deleting them is why the videos had ZERO shots under 1.5s against the
    reference's 22%."""
    plan = plan_shots(
        _sl(["p1", "p2", "p3"]),
        {1: [{"seconds": 2.4}]},
        floor=1.0,
        accent_floor=0.4,
    )
    assert [pid for pid, _ in plan[1]] == ["p1", "p2", "p3"]
    assert all(abs(sec - 0.8) < 1e-6 for _, sec in plan[1])


def test_accent_below_accent_floor_still_merges():
    plan = plan_shots(
        _sl(["p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8"]),
        {1: [{"seconds": 2.4}]},
        floor=1.0,
        accent_floor=0.4,
    )
    assert all(sec >= 0.4 for _, sec in plan[1]), plan[1]
    assert abs(sum(sec for _, sec in plan[1]) - 2.4) < 1e-6


def test_fill_crosses_beat_boundaries():
    """Anchors in DIFFERENT beats still bound a fill run."""
    shotlist = {"sentences": [
        {"number": 1, "beat_id": 1, "text": "a", "panels": ["p1"]},
        {"number": 2, "beat_id": 1, "text": "b", "panels": []},
        {"number": 3, "beat_id": 2, "text": "c", "panels": []},
        {"number": 4, "beat_id": 2, "text": "d", "panels": ["p4"]},
    ]}
    segs = {1: [{"seconds": 2.0}, {"seconds": 2.0}], 2: [{"seconds": 2.0}, {"seconds": 2.0}]}
    plan = plan_shots(shotlist, segs, floor=1.0, panel_order=["p1", "p2", "p3", "p4"])
    shown = [pid for beat in (1, 2) for pid, _ in plan[beat]]
    assert shown == ["p1", "p2", "p3", "p4"], shown


def test_accent_bursts_are_capped():
    """Accent cuts are punctuation, not texture. The reference runs at most 3
    consecutive sub-1.2s shots (once in 10 minutes); our first cut ran bursts of 6,
    five times over — the user reported it as jarring."""
    plan = plan_shots(
        _sl(*[["p%d" % i] for i in range(1, 11)]),
        {1: [{"seconds": 0.9}] * 10},
        floor=0.5,
        accent_floor=0.4,
    )
    durs = [sec for _pid, sec in plan[1]]
    runs = []
    cur = 0
    for d in durs:
        if d < 1.2:
            cur += 1
        else:
            runs.append(cur)
            cur = 0
    runs.append(cur)
    assert max(runs) <= 3, f"burst of {max(runs)} short shots survived: {durs}"
    assert abs(sum(durs) - 9.0) < 1e-6, "A/V total preserved through burst merging"


def test_bubble_only_panel_is_swapped_for_its_art():
    """A claimed panel that is nothing but a speech bubble becomes a wall of text on
    the page background. The narrator is already speaking that line, so the screen
    shows the nearest art instead — the reference channel never frames a bare bubble."""
    order = ["p1", "p2", "p3", "p4"]
    plan = plan_shots(
        _sl(["p1"], ["p2"], ["p4"]),
        {1: [{"seconds": 2.0}, {"seconds": 2.0}, {"seconds": 2.0}]},
        floor=1.0,
        panel_order=order,
        text_only={"p2"},
    )
    shown = [pid for pid, _ in plan[1]]
    assert "p2" not in shown, f"bare bubble still on screen: {shown}"
    assert abs(sum(s for _, s in plan[1]) - 6.0) < 1e-6


def test_fill_never_volunteers_a_bubble_panel():
    order = ["p1", "p2", "p3", "p4", "p5"]
    plan = plan_shots(
        _sl(["p1"], [], ["p5"]),
        {1: [{"seconds": 2.0}, {"seconds": 3.0}, {"seconds": 2.0}]},
        floor=1.0,
        panel_order=order,
        text_only={"p3"},
    )
    assert "p3" not in [pid for pid, _ in plan[1]]


def test_all_text_only_leaves_the_claim_alone():
    """No art anywhere to swap to: keep the claim rather than emptying the shot."""
    plan = plan_shots(
        _sl(["p1"]),
        {1: [{"seconds": 3.0}]},
        floor=1.0,
        panel_order=["p1"],
        text_only={"p1"},
    )
    assert plan[1] == [("p1", 3.0)]


def test_a_beat_does_not_open_on_the_panel_the_last_one_closed_on():
    """An invisible cut: two planned shots the viewer reads as one long hold.

    Holding across a beat boundary is the deliberate fallback for an unclaimed opening
    sentence, but nothing downstream can tell the difference — the dwell limit and the
    burst guard both count PLANNED entries. Frozen Player ch1-2 shipped 6 of these,
    making 106 planned shots into 100 seen ones and a 16.7s longest shot into 18.6s.
    """
    plan = plan_shots(
        {"sentences": [
            {"beat_id": 1, "panels": ["p1"]},
            {"beat_id": 1, "panels": ["p2"]},
            {"beat_id": 2, "panels": ["p2"]},   # opens on what beat 1 closed on
            {"beat_id": 2, "panels": ["p4"]},
        ]},
        {1: [{"seconds": 3.0}, {"seconds": 3.0}], 2: [{"seconds": 3.0}, {"seconds": 3.0}]},
        floor=1.0,
        panel_order=["p1", "p2", "p3", "p4"],
    )
    assert plan is not None
    assert plan[1][-1][0] == "p2"
    assert plan[2][0][0] == "p3", "should advance to the next unclaimed panel, not repeat"


def test_the_hold_survives_when_every_panel_is_already_shown():
    """An unrelated image is worse than a repeated one — keep the hold rather than
    reaching for a panel that has nothing to do with the line.

    The search looks BOTH ways in reading order now, so "nothing to advance to" means
    genuinely nothing unused anywhere, not merely nothing after this panel."""
    plan = plan_shots(
        {"sentences": [
            {"beat_id": 1, "panels": ["p1"]},
            {"beat_id": 1, "panels": ["p2"]},
            {"beat_id": 2, "panels": ["p2"]},
        ]},
        {1: [{"seconds": 3.0}, {"seconds": 3.0}], 2: [{"seconds": 3.0}]},
        floor=1.0,
        panel_order=["p1", "p2"],   # both already claimed
    )
    assert plan is not None
    assert plan[2][0][0] == "p2"


def test_an_over_long_shot_is_split_across_a_spare_panel():
    """Solo Leveling shipped one image held 27.8s and Frozen Player 18.6s, both from a
    beat carrying more narration than it has panels. The reference's own longest is
    16.37s."""
    plan = plan_shots(
        {"sentences": [
            {"number": 1, "beat_id": 1, "panels": ["p1"]},
            {"number": 2, "beat_id": 1, "panels": ["p1"]},
        ]},
        {1: [{"seconds": 7.0}, {"seconds": 7.0}]},
        floor=1.0,
        panel_order=["p1", "p2", "p3"],
        max_shot=10.0,
    )
    assert plan is not None
    assert max(sec for _pid, sec in plan[1]) <= 10.0
    assert {pid for pid, _sec in plan[1]} == {"p1", "p2"}
    assert abs(sum(sec for _pid, sec in plan[1]) - 14.0) < 1e-6, "A/V total preserved"


def test_a_very_long_beat_keeps_splitting_until_every_shot_is_legal():
    """The first half of a split can still be over the cap, so the pass re-examines it."""
    plan = plan_shots(
        {"sentences": [{"number": i, "beat_id": 1, "panels": ["p1"]} for i in range(1, 5)]},
        {1: [{"seconds": 6.0}] * 4},
        floor=1.0,
        panel_order=["p1", "p2", "p3", "p4"],
        max_shot=10.0,
    )
    assert plan is not None
    assert max(sec for _pid, sec in plan[1]) <= 10.0
    assert abs(sum(sec for _pid, sec in plan[1]) - 24.0) < 1e-6


def test_a_long_shot_at_the_chapter_end_keeps_the_dwell_rather_than_rewinding():
    """REVERSED 2026-08-30. This test used to pin backwards borrowing ("an unused panel
    is art the reader saw on the same pages either way"). Watching proved that wrong:
    an earlier panel shown after a later one is a REWIND on screen, whatever the reader
    once saw — 16 reading-order inversions on FP, jumps back by up to 71 panels, all
    from unconstrained borrows. With nothing unused AFTER the held panel, the long
    dwell stays; `dwell-over-limit` reports it, and a long shot beats a wrong image."""
    plan = plan_shots(
        {"sentences": [
            {"number": 1, "beat_id": 1, "panels": ["p3"]},
            {"number": 2, "beat_id": 1, "panels": ["p3"]},
        ]},
        {1: [{"seconds": 9.0}, {"seconds": 9.0}]},
        floor=1.0,
        panel_order=["p1", "p2", "p3"],
        max_shot=10.0,
    )
    assert plan is not None
    assert [pid for pid, _sec in plan[1]] == ["p3"], "a backwards borrow crept back in"
    assert abs(sum(sec for _pid, sec in plan[1]) - 18.0) < 1e-6


def test_a_single_sentence_shot_is_never_split():
    """Splitting inside one sentence would cut mid-thought; the planner only splits where
    a sentence boundary already exists."""
    plan = plan_shots(
        {"sentences": [{"number": 1, "beat_id": 1, "panels": ["p1"]}]},
        {1: [{"seconds": 30.0}]},
        floor=1.0,
        panel_order=["p1", "p2"],
        max_shot=10.0,
    )
    assert plan == {1: [("p1", 30.0)]}


def test_the_cap_is_off_by_default():
    """max_shot=0 keeps the previous behaviour, so every other test in this file still
    describes the planner it was written against."""
    plan = plan_shots(
        {"sentences": [{"number": 1, "beat_id": 1, "panels": ["p1"]},
                       {"number": 2, "beat_id": 1, "panels": ["p1"]}]},
        {1: [{"seconds": 20.0}, {"seconds": 20.0}]},
        floor=1.0, panel_order=["p1", "p2"],
    )
    assert plan == {1: [("p1", 40.0)]}


def test_a_hold_spanning_two_beats_is_broken_up():
    """Everything else in the planner works inside ONE beat, so a shot that is legal in
    beat N and legal in beat N+1 is still one long hold on screen: 7.2s + 7.2s on the same
    panel is 14.4s to a viewer. Frozen Player shipped exactly that."""
    plan = plan_shots(
        {"sentences": [
            {"number": 1, "beat_id": 1, "panels": ["p2"]},
            {"number": 2, "beat_id": 2, "panels": ["p2"]},
        ]},
        {1: [{"seconds": 7.2}], 2: [{"seconds": 7.2}]},
        floor=1.0,
        panel_order=["p1", "p2", "p3"],
        max_shot=10.0,
    )
    assert plan is not None
    assert plan[1][0][0] != plan[2][0][0], "the viewer must see a cut between the beats"
    assert abs(plan[1][0][1] + plan[2][0][1] - 14.4) < 1e-6, "A/V total preserved"


class TestShotlistArtifacts:
    """build_shotlist's two side artifacts: the outro marker and the claims debug file."""

    @staticmethod
    def _panel(pid):
        from manhwa2vid.models import Panel, PanelBBox

        return Panel(id=pid, page_num=1, bbox=PanelBBox(x=0, y=0, width=10, height=10),
                     image_path=f"panels/{pid}.png")

    def _run(self, tmp_path, beats):
        from manhwa2vid.script.match import build_shotlist

        panels = [self._panel(f"p{i:02d}") for i in range(6)]
        n = sum(len(s) for _b, s in beats)
        paths = {
            "root": tmp_path,
            "debug": tmp_path / "debug",
            "script_shotlist_json": tmp_path / "script.shotlist.json",
        }
        return build_shotlist(beats, [panels], [0] * n, paths, {}), paths

    def test_outro_sentences_are_marked(self, tmp_path, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        shotlist, _ = self._run(tmp_path, [
            (1, ["He draws his blade.", "She nods once."]),
            (2, ["Subscribe and turn notifications on.", "Every second counts."]),
        ])
        flags = [s.get("outro", False) for s in shotlist["sentences"]]
        assert flags == [False, False, True, True]

    def test_a_final_beat_without_an_ask_is_not_an_outro(self, tmp_path, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        shotlist, _ = self._run(tmp_path, [
            (1, ["He draws his blade."]),
            (2, ["The gate slams shut."]),
        ])
        assert not any(s.get("outro") for s in shotlist["sentences"])

    def test_raw_claims_are_persisted_for_diagnosis(self, tmp_path, monkeypatch):
        """Until this file existed, the only trace of what the model claimed before the
        monotonic filter was a console line — diagnosing a drop meant re-paying every
        vision call."""
        import json as _json

        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        _, paths = self._run(tmp_path, [(1, ["One.", "Two.", "Three.", "Four."])])
        data = _json.loads((paths["debug"] / "match_claims.json").read_text())
        assert data["blocks"], "no block record written"
        block = data["blocks"][0]
        assert set(block) >= {"block", "sentences", "panels", "raw", "kept"}
        assert len(block["kept"]) <= len(block["raw"])


class TestWindowScoping:
    """Every window used to see the ENTIRE block's sentence list (~174 sentences against
    16 panels on Solo Leveling's block 0), so distant windows claimed the same sentences
    and the monotonic filter destroyed all but one of each set — ~30% of raw claims died
    as duplicates, and every death read as an unmatched sentence in the gate."""

    @staticmethod
    def _panel(pid, page):
        from manhwa2vid.models import Panel, PanelBBox

        return Panel(id=pid, page_num=page, bbox=PanelBBox(x=0, y=0, width=10, height=10),
                     image_path=f"panels/{pid}.png")

    SENTS = [(1, "One."), (2, "Two."), (3, "Three."), (4, "Four.")]

    def test_a_window_only_sees_sentences_near_its_pages(self):
        from manhwa2vid.script.match import _window_sentences

        batch = [self._panel("a", 10), self._panel("b", 11)]
        pages = {1: (1, 2), 2: (9, 12), 3: (10, 11), 4: (30, 33)}
        scoped = _window_sentences(self.SENTS, batch, pages)
        assert [n for n, _ in scoped] == [2, 3]

    def test_no_map_means_the_old_behaviour(self):
        from manhwa2vid.script.match import _window_sentences

        batch = [self._panel("a", 10)]
        assert _window_sentences(self.SENTS, batch, None) == self.SENTS
        assert _window_sentences(self.SENTS, batch, {}) == self.SENTS

    def test_a_sentence_the_map_missed_is_in_scope_everywhere(self):
        from manhwa2vid.script.match import _window_sentences

        batch = [self._panel("a", 10)]
        pages = {1: (1, 2), 2: (9, 12)}  # 3 and 4 unmapped
        scoped = _window_sentences(self.SENTS, batch, pages)
        assert [n for n, _ in scoped] == [2, 3, 4]

    def test_a_collapsed_map_falls_back_to_the_full_list(self):
        """If the advisory map maps everything far from this window, excluding all
        sentences would silence the window entirely — worse than the duplicates."""
        from manhwa2vid.script.match import _window_sentences

        batch = [self._panel("a", 50)]
        pages = {n: (1, 2) for n, _ in self.SENTS}
        assert _window_sentences(self.SENTS, batch, pages) == self.SENTS


class TestSentencePageRanges:
    def test_ranges_widen_by_one_paragraph_each_side(self):
        from manhwa2vid.script.align import _sentence_page_ranges

        paras = ["First one. Second one.", "Third one."]
        amap = [
            {"paragraph": 1, "first_page": 1, "last_page": 3},
            {"paragraph": 2, "first_page": 4, "last_page": 6},
        ]
        r = _sentence_page_ranges(paras, amap)
        # paragraph 1's sentences may also sit in paragraph 2's pages, and vice versa
        assert r[1] == (1, 6) and r[2] == (1, 6) and r[3] == (1, 6)

    def test_interior_paragraph_does_not_inherit_distant_pages(self):
        from manhwa2vid.script.align import _sentence_page_ranges

        paras = ["A one.", "B one.", "C one.", "D one."]
        amap = [{"paragraph": i, "first_page": i * 10, "last_page": i * 10 + 5}
                for i in range(1, 5)]
        r = _sentence_page_ranges(paras, amap)
        assert r[2] == (10, 35)   # paragraphs 1..3
        assert r[3] == (20, 45)   # paragraphs 2..4

    def test_an_unmapped_paragraph_contributes_no_range(self):
        from manhwa2vid.script.align import _sentence_page_ranges

        paras = ["A one.", "B one."]
        amap = [{"paragraph": 1, "first_page": 1, "last_page": 2}]
        r = _sentence_page_ranges(paras, amap)
        assert 1 in r and 2 not in r

    def test_garbage_map_entries_are_skipped(self):
        from manhwa2vid.script.align import _sentence_page_ranges

        paras = ["A one."]
        amap = [{"paragraph": "x"}, {"first_page": 1}, None if False else {}]
        assert _sentence_page_ranges(paras, amap) == {}


def test_filter_prefers_distinct_sentences_over_one_sentences_accent_pile():
    """The longest-chain objective let one sentence's accent panels outcompete other
    sentences' ONLY panels: Solo Leveling's first block claimed 136 distinct sentences
    and the longest chain kept 87. The DP now maximises distinct sentences first."""
    from manhwa2vid.script.match import filter_monotonic

    order = ["pa", "pb", "pc", "pd"]
    claims = [(1, "pa"), (1, "pb"), (1, "pc"), (1, "pd"),  # one sentence, four panels
              (2, "pb"), (3, "pc")]                          # two sentences, one each
    kept = filter_monotonic(claims, order)
    assert {n for n, _ in kept} == {1, 2, 3}, "two sentences were starved for accents"


def test_filter_still_keeps_accents_when_they_cost_nothing():
    from manhwa2vid.script.match import filter_monotonic

    order = ["pa", "pb", "pc"]
    claims = [(1, "pa"), (1, "pb"), (2, "pc")]
    kept = filter_monotonic(claims, order)
    assert kept == [(1, "pa"), (1, "pb"), (2, "pc")]


def test_a_bare_list_response_is_accepted_as_the_claims_array():
    """The matcher LLM sometimes returns the claims array bare instead of wrapped in
    {"claims": [...]}. `data.get` then raised AttributeError, align.py's blanket except
    swallowed it, and the run continued with NO shotlist — twice on Solo Leveling in
    one day, with binding silently degraded to airtime weighting both times."""
    import json as _json

    from manhwa2vid.script import match as M

    class _Provider:
        temperature = 0.0
        vision_model = None

        def describe_labeled_panels(self, *_a, **_k):
            return _json.dumps([
                {"sentence": 1, "panels": ["p1"]},
                "not-a-dict-claim-must-be-skipped",
                {"sentence": "junk"},
            ])

    class _Panel:
        def __init__(self, pid):
            self.id = pid
            self.image_path = f"panels/{pid}.png"

    import manhwa2vid.llm.provider as prov
    orig = prov.get_llm_provider
    prov.get_llm_provider = lambda *_a, **_k: _Provider()
    try:
        claims = M.collect_claims(
            [(1, "He draws his blade.")], [_Panel("p1")],
            {"root": __import__("pathlib").Path(".")}, {},
        )
    finally:
        prov.get_llm_provider = orig
    assert claims == [(1, "p1")]
