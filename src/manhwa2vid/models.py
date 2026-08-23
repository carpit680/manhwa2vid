"""Data models for pipeline artifacts."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator


class SourceLanguage(str, Enum):
    KO = "ko"
    EN = "en"


class SourceType(str, Enum):
    PDF = "pdf"
    IMAGES = "images"


class VisualMode(str, Enum):
    PANELS = "panels"
    PANELS_TRANSFORMED = "panels_transformed"
    NARRATION_ONLY = "narration_only"


class ProjectMeta(BaseModel):
    slug: str
    title: str
    chapters: str
    source_lang: SourceLanguage
    source_type: SourceType = SourceType.PDF
    source_path: str = ""
    pdf_path: str = ""  # legacy alias for PDF projects
    images_are_panels: bool = False
    visual_mode: VisualMode = VisualMode.PANELS
    commentary_level: str = "light"
    series_slug: str = ""

    @model_validator(mode="after")
    def resolve_source_fields(self) -> ProjectMeta:
        if not self.source_path and self.pdf_path:
            self.source_path = self.pdf_path
        if not self.pdf_path and self.source_path:
            self.pdf_path = self.source_path
        if self.source_type == SourceType.IMAGES and not self.images_are_panels:
            self.images_are_panels = True
        if not self.series_slug:
            import re

            self.series_slug = re.sub(r"[^a-z0-9]+", "-", self.title.lower()).strip("-")
        return self


class PageInfo(BaseModel):
    page_num: int
    filename: str
    width: int
    height: int


class PanelBBox(BaseModel):
    x: int
    y: int
    width: int
    height: int


class Panel(BaseModel):
    id: str
    page_num: int
    bbox: PanelBBox
    image_path: str
    confidence: float = 1.0
    split_method: str = "auto"
    aspect_ratio: float | None = None
    camera_hint: str = "auto"  # auto | scroll | ken_burns
    # Pixel-content stats stamped at split time (None on pre-change cached panels.json;
    # backfilled lazily by apply_panel_filter). Used to exclude blank transition slivers.
    ink_ratio: float | None = None   # fraction of pixels with gray < 245
    dark_ratio: float | None = None  # fraction of pixels with gray < 128


class PageSplitResult(BaseModel):
    page_num: int
    panels: list[Panel]
    confidence: float
    split_method: str
    low_confidence: bool = False


class OCRLine(BaseModel):
    text: str
    confidence: float
    bbox: list[int] = Field(default_factory=list)


class PanelOCR(BaseModel):
    panel_id: str
    lines: list[OCRLine]
    full_text: str = ""
    translated_text: str = ""


class CharacterTier(str, Enum):
    MAIN = "main"
    SUPPORTING = "supporting"
    MINOR = "minor"
    EXTRA = "extra"


class CharacterRef(BaseModel):
    ref: str = "new"  # char_id or "new"
    name_used: str = ""
    descriptor: str = ""
    visibility: str = "face"  # face | back_turned | partial | crowd
    notes: str = ""
    # The vision model's own certainty that this is that specific cast member (0-1).
    # 0.0 on pre-change cached cards. Only high-confidence identifications may become
    # reference images — a shaky one would make identity confusion self-reinforcing.
    confidence: float = 0.0


class VisualProfile(BaseModel):
    hair: str = ""
    outfit: str = ""
    build: str = ""
    accessories: list[str] = Field(default_factory=list)
    age_range: str = ""
    notes: str = ""


class CharacterProfile(BaseModel):
    id: str
    canonical_name: str
    tier: CharacterTier = CharacterTier.MINOR
    aliases: list[str] = Field(default_factory=list)
    descriptors: list[str] = Field(default_factory=list)
    pronoun: str = "they"
    role: str = ""
    first_seen_panel: str = ""
    appearances: list[str] = Field(default_factory=list)
    visual: VisualProfile = Field(default_factory=VisualProfile)
    narration_labels: list[str] = Field(default_factory=list)
    sufficiency: str = "pending"  # pending | sufficient | partial | abandoned
    confidence: float = 0.0
    merged_into: str = ""
    source_chapters: list[int] = Field(default_factory=list)


class PanelCast(BaseModel):
    panel_id: str
    people: list[CharacterRef] = Field(default_factory=list)


class CharacterFinding(BaseModel):
    """Evidence gathered during a character quest iteration."""

    field: str = ""
    value: str = ""
    source: str = ""  # wiki | scout_panel | current_ocr | current_scene | glossary
    chapter: int | None = None
    confidence: float = 0.5


class CharacterQuestState(BaseModel):
    char_id: str
    iterations: int = 0
    gaps: list[str] = Field(default_factory=list)
    sources_used: list[str] = Field(default_factory=list)
    status: str = "pending"  # pending | sufficient | partial | abandoned


class SeriesBible(BaseModel):
    series_slug: str
    title: str
    characters: dict[str, CharacterProfile] = Field(default_factory=dict)
    chapter_summaries: dict[str, str] = Field(default_factory=dict)
    protagonist_id: str = ""
    quest_completed: bool = False


class SceneCard(BaseModel):
    panel_ids: list[str]
    speakers: list[str] = Field(default_factory=list)
    dialogue_summary: str = ""
    action: str = ""
    mood: str = ""
    key_terms: list[str] = Field(default_factory=list)
    source_text: str = ""
    is_story: bool = True
    exclude_reason: str = ""
    panel_type: str = "story"  # story | title_splash | credit | ad | other
    people: list[CharacterRef] = Field(default_factory=list)


class ScriptBeat(BaseModel):
    beat_id: int
    panel_ids: list[str]
    narration: str
    estimated_seconds: float | None = None
    character_ids: list[str] = Field(default_factory=list)
    # Panels this beat's narration DEPENDS on — the moment named, the emotion described,
    # the blow landed. Marked by the writer (which read the evidence), editable in the
    # draft markdown, honored by timeline curation: key panels are always shown.
    key_panel_ids: list[str] = Field(default_factory=list)


class ScriptOutlineBeat(BaseModel):
    beat_id: int
    panel_ids: list[str]
    character_ids: list[str] = Field(default_factory=list)
    plot_beat: str = ""
    #: Synopsis facts that bind to no single panel well enough to seed a beat of their
    #: own. They used to be dropped, taking the chapter's payoffs with them: Frozen
    #: Player's "the 3rd floor needs the Frost Queen's nucleus" and "Frost (EX) can melt
    #: his comrades' seals" are what the reference channel builds its climax on, and
    #: neither reached our narration. Carried to the nearest beat and shown to the writer.
    required_context: list[str] = Field(default_factory=list)
    is_closer: bool = False  # final beat: next-chapter hook written from open_threads


class NamedCastEntry(BaseModel):
    name: str
    char_id: str = ""
    role: str = ""
    descriptors: list[str] = Field(default_factory=list)
    notes: str = ""


class ChapterSynopsis(BaseModel):
    logline: str = ""
    arc: list[str] = Field(default_factory=list)
    named_cast: list[NamedCastEntry] = Field(default_factory=list)
    plot_facts: list[str] = Field(default_factory=list)
    open_threads: list[str] = Field(default_factory=list)
    # Narrative devices the chapter uses (cold-open flashforward, flashback, time skip)
    # and where the frame shifts happen. Narration must SPEAK these transitions; panels
    # are not strictly chronological and pretending they are confuses viewers.
    narrative_structure: str = ""


class ScriptDraft(BaseModel):
    title: str
    chapters: str
    beats: list[ScriptBeat]
    hook: str = ""


class TimelineEntry(BaseModel):
    panel_id: str
    panel_path: str
    start: float
    end: float
    duration: float
    audio_file: str | None = None
    subtitle_text: str = ""
    beat_id: int | None = None


class Timeline(BaseModel):
    entries: list[TimelineEntry]
    total_duration: float
    fps: int = 30
    dropped_panels: int = 0  # panels the per-beat budget removed (see budget_panels_for_beat)


class PipelineStage(str, Enum):
    INGEST = "ingest"
    PANELS = "panels"
    STORY = "story"
    SCOUT = "scout"
    OCR = "ocr"
    SCENE = "scene"
    CAST = "cast"
    SCRIPT = "script"
    TTS = "tts"
    TIMELINE = "timeline"
    RENDER = "render"
    EXPORT = "export"


class CheckpointState(BaseModel):
    completed_stages: list[PipelineStage] = Field(default_factory=list)
    script_approved: bool = False
    preview_approved: bool = False


def series_paths(repo_root: Path, series_slug: str) -> dict[str, Path]:
    base = repo_root / "projects" / series_slug / "series"
    scout = base / "scout"
    return {
        "series_dir": base,
        "character_bible": base / "character_bible.json",
        "character_quest": base / "character_quest.json",
        "scout_dir": scout,
        "scout_manifest": scout / "manifest.json",
        "story_map": base / "story_map.json",
    }


def project_paths(project_dir: Path) -> dict[str, Path]:
    """Standard artifact paths for a project directory."""
    return {
        "root": project_dir,
        "meta": project_dir / "project.json",
        "checkpoint": project_dir / "checkpoint.json",
        "glossary": project_dir / "glossary.json",
        "pages": project_dir / "pages",
        "panels": project_dir / "panels",
        "panels_json": project_dir / "panels.json",
        "panels_story_json": project_dir / "panels.story.json",
        "panels_curated_json": project_dir / "panels.curated.json",
        "excluded_panels_json": project_dir / "excluded_panels.json",
        "ocr_json": project_dir / "ocr.json",
        "scene_json": project_dir / "scene_cards.json",
        "scene_partial_json": project_dir / "scene_cards.partial.json",
        "scene_enriched_json": project_dir / "scene_cards.enriched.json",
        "corrections_json": project_dir / "corrections.json",
        "scene_normalized_json": project_dir / "scene_cards.normalized.json",
        # Chapter-mode only: the whole-chapter reading the vision pass produced before
        # annotating individual panels (arc summary + temporal devices).
        "scene_story_map_json": project_dir / "scene_story_map.json",
        "cast_attribution_json": project_dir / "cast_attribution.json",
        "script_synopsis_json": project_dir / "script.synopsis.json",
        "script_outline_json": project_dir / "script.outline.json",
        "script_draft": project_dir / "script.draft.md",
        "script_final": project_dir / "script.final.md",
        "script_json": project_dir / "script.json",
        "audio": project_dir / "audio",
        "timeline_json": project_dir / "timeline.json",
        "output": project_dir / "output",
        "debug": project_dir / "debug",
    }


def save_json(path: Path, data: BaseModel | dict[str, Any] | list[Any]) -> None:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, BaseModel):
        payload = data.model_dump(mode="json")
    elif isinstance(data, list):
        payload = [item.model_dump(mode="json") if isinstance(item, BaseModel) else item for item in data]
    else:
        payload = data
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def load_json(path: Path, model: type[BaseModel]) -> BaseModel:
    import json

    return model.model_validate(json.loads(path.read_text(encoding="utf-8")))
