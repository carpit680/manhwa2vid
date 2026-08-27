"""The closing ask, written into the narration instead of stapled on after it."""

from __future__ import annotations

from manhwa2vid.models import ProjectMeta, SourceLanguage, SourceType
from manhwa2vid.script.outro import append_outro


def _meta() -> ProjectMeta:
    return ProjectMeta(
        slug="t", title="Return of the Frozen Player", chapters="1-2",
        source_lang=SourceLanguage.EN, source_type=SourceType.IMAGES,
        source_path="/tmp", pdf_path="/tmp",
    )


def test_outro_continues_the_narration_and_asks(monkeypatch):
    text = "He reaches up, wiping dust off her frozen face.\n\nA second prompt flips the script."
    out = append_outro(text, _meta(), {}, {"llm": {"provider": "mock"}})
    assert out.startswith(text.rstrip()), "the story text must be untouched"
    assert "subscri" in out.lower(), "the ask has to be in there"
    tail = out[len(text.rstrip()):].strip()
    assert 1 <= len([s for s in tail.split(". ") if s.strip()]) <= 2
    for banned in ("guys", "this video", "the channel", "like and subscribe"):
        assert banned not in tail.lower()


def test_outro_can_be_disabled():
    text = "The end of the chapter."
    assert append_outro(text, _meta(), {}, {"script": {"outro_cta": False}}) == text


def test_empty_text_is_left_alone():
    assert append_outro("", _meta(), {}, {}) == ""
    assert append_outro("   ", _meta(), {}, {}).strip() == ""


def test_a_bad_model_outro_is_rejected_for_the_fixed_one(monkeypatch):
    """Shape is checked absolutely: a rambling or off-brief outro is replaced, not
    shipped. The model gets two sentences and no marketing vocabulary."""
    import manhwa2vid.llm.provider as prov

    class Bad:
        def complete(self, system, user):
            return ("Hey guys welcome back to the channel, in today's video we covered "
                    "so much. Please like and subscribe. And comment below. And more.")

    monkeypatch.setattr(prov, "get_llm_provider", lambda *a, **k: Bad())
    out = append_outro("Story ends here.", _meta(), {}, {})
    tail = out[len("Story ends here."):].strip()
    assert "guys" not in tail.lower() and "subscri" in tail.lower()


def test_running_the_stage_twice_does_not_double_the_outro():
    """The script stage is re-runnable and append_outro is called on the freeform text
    each time. Appending a second ask would be a silent defect that only shows up in the
    finished audio."""
    text = "He wipes the dust from her frozen face."
    once = append_outro(text, _meta(), {}, {})
    twice = append_outro(once, _meta(), {}, {})
    assert twice.lower().count("subscri") == 1, "a second outro was appended"
