"""Pipeline stage orchestration."""

from __future__ import annotations

import os

import json
from pathlib import Path

from rich.console import Console

from manhwa2vid.config import get_nested, load_config
from manhwa2vid.export.youtube import export_youtube_pack
from manhwa2vid.ingest import ingest_source
from manhwa2vid.models import (
    CheckpointState,
    PipelineStage,
    ProjectMeta,
    load_json,
    project_paths,
    save_json,
)
from manhwa2vid.characters.link import run_cast_linking
from manhwa2vid.characters.scout import run_character_scout
from manhwa2vid.ocr.extract import run_ocr_and_scenes
from manhwa2vid.panels.split import split_panels
from manhwa2vid.script.generate import generate_script
from manhwa2vid.tts.engine import run_tts_and_timeline
from manhwa2vid.video.render import render_video

console = Console()


def load_project(project_dir: Path) -> tuple[ProjectMeta, dict[str, Path], dict, CheckpointState]:
    paths = project_paths(project_dir)
    if not paths["meta"].exists():
        raise FileNotFoundError(f"Project not found: {project_dir}")
    meta = load_json(paths["meta"], ProjectMeta)
    config = load_config()
    checkpoint = (
        load_json(paths["checkpoint"], CheckpointState)
        if paths["checkpoint"].exists()
        else CheckpointState()
    )
    return meta, paths, config, checkpoint


def mark_stage(checkpoint: CheckpointState, stage: PipelineStage, paths: dict[str, Path]) -> None:
    if stage not in checkpoint.completed_stages:
        checkpoint.completed_stages.append(stage)
    save_json(paths["checkpoint"], checkpoint)


def run_stage(
    project_dir: Path,
    stage: PipelineStage,
    *,
    force: bool = False,
    preview: bool = False,
    final: bool = False,
    force_past_qa: bool = False,
    keep_upstream: bool = False,
) -> None:
    meta, paths, config, checkpoint = load_project(project_dir)
    if force_past_qa:
        config["_qa_force"] = True  # read by qa.qa_forced() inside stages

    if stage == PipelineStage.INGEST:
        ingest_source(meta, paths, config, force=force)
        mark_stage(checkpoint, stage, paths)
    elif stage == PipelineStage.PANELS:
        split_panels(meta, paths, config, force=force)
        mark_stage(checkpoint, stage, paths)
    elif stage == PipelineStage.STORY:
        from manhwa2vid.story.brief import run_story_pass

        run_story_pass(meta, paths, config, force=force)
        mark_stage(checkpoint, stage, paths)
    elif stage == PipelineStage.SCOUT:
        run_character_scout(meta, paths, config, force=force)
        mark_stage(checkpoint, stage, paths)
    elif stage in (PipelineStage.OCR, PipelineStage.SCENE):
        run_ocr_and_scenes(meta, paths, config, force=force)
        mark_stage(checkpoint, PipelineStage.OCR, paths)
        mark_stage(checkpoint, PipelineStage.SCENE, paths)
    elif stage == PipelineStage.CAST:
        run_cast_linking(meta, paths, config, force=force)
        mark_stage(checkpoint, stage, paths)
    elif stage == PipelineStage.SCRIPT:
        # Two architectures during the transition. "freeform" is the story-first path
        # (read -> write -> audit -> revise -> align); "classic" is the panel-locked
        # pipeline it replaces. See experiments/oneshot-fp-ch1-2/comparison.md.
        # Env wins over config, like every other provider selection in this codebase.
        # It also keeps tests from having to mutate the shared config.yaml, which made
        # the two pipeline tests race and fail on a different gate each run.
        architecture = os.getenv("SCRIPT_ARCHITECTURE") or str(
            get_nested(config, "script", "architecture", default="classic")
        )
        if architecture == "freeform":
            from manhwa2vid.script.story_first import generate_story_first_script

            generate_story_first_script(meta, paths, config, force=force)
        else:
            generate_script(meta, paths, config, force=force, keep_upstream=keep_upstream)
        mark_stage(checkpoint, stage, paths)
    elif stage == PipelineStage.TTS:
        if not paths["script_final"].exists() and not checkpoint.script_approved:
            raise RuntimeError(
                "Script not approved. Edit script.draft.md, save as script.final.md, "
                "or run: manhwa2vid review script --approve"
            )
        run_tts_and_timeline(meta, paths, config, force=force)
        mark_stage(checkpoint, PipelineStage.TTS, paths)
        mark_stage(checkpoint, PipelineStage.TIMELINE, paths)
    elif stage == PipelineStage.RENDER:
        if not paths["timeline_json"].exists():
            raise RuntimeError("Timeline missing. Run TTS stage first.")
        # A red gate anywhere upstream must stop the render: both 2026-08-26 audited
        # videos shipped while script-stage gates were FAILING — nothing connected a
        # failed gate to the render that published it.
        from manhwa2vid.video.qa_visual import upstream_failures

        failed = upstream_failures(project_dir)
        if failed and not force_past_qa:
            from manhwa2vid.qa import QAGateFailure

            raise QAGateFailure(
                "Refusing to render over failed upstream QA gates: "
                + ", ".join(failed)
                + ". Fix them or re-run with --force-past-qa."
            )
        if failed:
            console.print(
                f"[red]Rendering over failed upstream gate(s) ({', '.join(failed)}) "
                "— forced[/]"
            )
        render_video(meta, paths, config, preview=preview, final=final, force=force)
        mark_stage(checkpoint, stage, paths)
    elif stage == PipelineStage.EXPORT:
        export_youtube_pack(meta, paths, config)
        mark_stage(checkpoint, stage, paths)
    else:
        raise ValueError(f"Unknown stage: {stage}")


def run_all_until_review(project_dir: Path, force: bool = False, force_past_qa: bool = False) -> None:
    """Run ingest through script generation, stopping before TTS."""
    stages = [
        PipelineStage.INGEST,
        PipelineStage.PANELS,
        PipelineStage.STORY,
        PipelineStage.SCOUT,
        PipelineStage.OCR,
        PipelineStage.CAST,
        PipelineStage.SCRIPT,
    ]
    for stage in stages:
        console.print(f"[bold cyan]Running stage:[/] {stage.value}")
        run_stage(project_dir, stage, force=force, force_past_qa=force_past_qa)
    console.print(
        "[yellow]Pipeline paused for script review.[/]\n"
        f"Edit: {project_paths(project_dir)['script_draft']}\n"
        "Save approved version as script.final.md, then:\n"
        "  manhwa2vid review script --approve\n"
        "  manhwa2vid run tts --project ..."
    )


def init_glossary(paths: dict[str, Path]) -> None:
    if not paths["glossary"].exists():
        save_json(
            paths["glossary"],
            {"characters": {}, "terms": {}, "notes": "Edit character names and power-system terms."},
        )
