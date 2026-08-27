"""Series character bible — cast context for the vision pass.

Reduced to what OCR needs. The scout/quest/link/consolidate machinery that used to
live here (accumulated per-panel identity state across chapters) is gone: the
story-first script path identifies characters from `glossary.json`, a flat
human-editable name -> aliases map that cannot drift the way accumulated state did —
it once elected a protagonist called "large orange demon" and pronounced the lead
"they" off 174 polluted descriptors.
"""

from manhwa2vid.characters.bible import format_bible_for_prompt, load_series_bible, save_series_bible
from manhwa2vid.characters.seed import seed_series_bible

__all__ = [
    "format_bible_for_prompt",
    "load_series_bible",
    "save_series_bible",
    "seed_series_bible",
]
