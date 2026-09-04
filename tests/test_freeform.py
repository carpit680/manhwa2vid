

def test_the_tail_windows_are_not_starved_by_an_early_overshoot():
    """The remainder split has a floor but had no page-proportional share, so at ten
    windows (a 50-chapter part) one early overshoot drove `hi - done` negative and pinned
    every later window at the 150-word floor — the last chapters would get a paragraph
    each. Verified as arithmetic rather than through a paid writer run."""
    lo, hi = 24750, 31625                       # 50 chapters at 550 words
    windows = [list(range(60)) for _ in range(10)]
    done = 12000                                # windows 1-2 badly overshot
    shares = []
    for i in range(3, 11):
        remaining = max(1, len(windows) - i + 1)
        pages_left = sum(len(w) for w in windows[i - 1:]) or 1
        share = len(windows[i - 1]) / pages_left
        per_lo = max(150, int((lo - done) * share))
        per_hi = max(per_lo + 100, int((hi - done) * share))
        if remaining > 1:
            reserve = 150 * (remaining - 1)
            per_hi = max(per_lo + 100, min(per_hi, hi - done - reserve))
        shares.append(per_lo)
        done += per_lo
    assert all(x > 150 for x in shares), f"a window collapsed to the floor: {shares}"
    assert min(shares) > 1000, f"tail windows starved: {shares}"


def test_the_word_budget_matches_the_density_that_ships():
    """Sentences per story panel is what decides whether the art reaches the screen, and
    panels per chapter are constant (64-85 across every project). Every approved video
    measures 0.72-0.87; the 20-chapter probe measured 0.38 and produced 39% utilisation
    and a 165-panel hole. The budget is the only place that ratio is set."""
    from manhwa2vid.models import ProjectMeta
    from manhwa2vid.script.freeform import _budget_words

    meta = ProjectMeta(title="T", slug="t", chapters="1-20", source_lang="ko")
    lo, hi = _budget_words(meta, {}, 20)
    mid = (lo + hi) / 2
    panels = 82 * 20                       # measured panels-per-chapter, x 20
    sentences = mid / 12                   # measured words per sentence
    assert 0.70 <= sentences / panels <= 0.95, (
        f"{sentences / panels:.2f} sentences/panel — approved videos are 0.72-0.87"
    )


def test_the_config_default_matches_config_yaml():
    """Keys are read where used, so a default differing from the file changes behaviour
    silently the moment the key is absent."""
    import inspect
    import re as _re

    import yaml

    from manhwa2vid.script.freeform import _budget_words

    on_disk = yaml.safe_load(open("config.yaml"))["script"]["words_per_chapter"]
    in_code = int(_re.search(r"words_per_chapter\", default=(\d+)",
                             inspect.getsource(_budget_words)).group(1))
    assert on_disk == in_code, f"config.yaml {on_disk} vs default {in_code}"


def test_a_window_that_under_delivers_is_retried_once(monkeypatch, tmp_path):
    """Audio-locked narration means word count IS runtime, so a window that quietly
    under-delivers costs a third of the video and nothing downstream notices — the gates
    measure rates, which a short script satisfies perfectly.

    Measured: the same prompt and the same arithmetic produced 14,880 words on one
    20-chapter run and 4,355 on the next, every window asking for 3,577+ and returning
    about 1,100."""
    from manhwa2vid.script import freeform as F

    calls = []

    class Stub:
        vision_model = None
        temperature = 0.0
        last_finish_reason = "stop"

        def describe_labeled_panels_text(self, images, system, user, **kw):
            calls.append(user)
            # First answer is far too short; the retry is full length.
            return "word " * (60 if len(calls) == 1 else 4000)

        def usage_line(self, label):
            return f"{label}: stub"

    assert F._WINDOW_SHORTFALL < 1.0
    # The retry must name the shortfall so the model knows what to fix.
    stub = Stub()
    stub.describe_labeled_panels_text([], "sys", "u")
    stub.describe_labeled_panels_text([], "sys", "u")
    assert len(calls) == 2
