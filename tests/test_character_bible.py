"""Character-bible invariants that only misbehave at multi-chapter scale."""

from manhwa2vid.characters.bible import effective_pronoun, infer_pronoun_from_descriptors
from manhwa2vid.models import CharacterProfile

def _profile(cid: str, descriptors: list[str], pronoun: str = "they") -> CharacterProfile:
    return CharacterProfile(id=cid, canonical_name=cid, pronoun=pronoun, descriptors=descriptors)


def test_pronoun_inference_survives_descriptor_pollution():
    """A five-chapter Solo Leveling run narrated "They grit his teeth" about the lead.

    His profile had accumulated 174 descriptors — 131 saying "man", 20 saying "woman"
    from other characters leaking in during cast merges — and the old rule required the
    opposing count to be exactly ZERO. That is a purity test where a majority test was
    wanted, and it fails harder the more evidence there is, so it abstained on the single
    best-evidenced character in the bible.
    """
    lopsided = _profile("mc", ["young man with black hair"] * 131 + ["woman with orange hair"] * 20)
    assert infer_pronoun_from_descriptors(lopsided) == "he"
    assert effective_pronoun(lopsided) == "he"


def test_pronoun_inference_still_abstains_on_a_genuinely_mixed_profile():
    """The ratio must not become a licence to guess.

    An 11-vs-28 profile in the same bible is polluted rather than lopsided, and inventing
    a pronoun for it is how a misgendered narration line ships. Unanimous-but-thin
    evidence still decides, which is what the Frozen Player cases depend on.
    """
    mixed = _profile("m", ["woman in a tan coat"] * 11 + ["man in a blue jacket"] * 28)
    assert infer_pronoun_from_descriptors(mixed) == ""
    assert effective_pronoun(mixed) == "they"

    assert infer_pronoun_from_descriptors(_profile("s", ["woman in white robes"] * 3)) == "she"
    assert infer_pronoun_from_descriptors(_profile("t", ["man in a cowboy hat"] * 8)) == "he"
    assert infer_pronoun_from_descriptors(_profile("u", ["man in a red jacket"])) == ""
