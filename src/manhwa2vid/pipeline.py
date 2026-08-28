"""Pipeline stage orchestration."""

from __future__ import annotations

import os

import json
from pathlib import Path
from typing import Any

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
from manhwa2vid.ocr.extract import run_ocr_and_scenes
from manhwa2vid.panels.split import split_panels
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
    i_understand: bool = False,
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
    elif stage in (PipelineStage.OCR, PipelineStage.SCENE):
        run_ocr_and_scenes(meta, paths, config, force=force)
        mark_stage(checkpoint, PipelineStage.OCR, paths)
        mark_stage(checkpoint, PipelineStage.SCENE, paths)
    elif stage == PipelineStage.SCRIPT:
        # Story-first, and now the only path: read the pages -> write the narration as
        # prose -> audit it against the pages -> revise once -> align paragraphs to
        # panels -> match sentences to the panels that depict them. The panel-locked
        # architecture it replaced is gone (see docs/history/).
        from manhwa2vid.script.story_first import generate_story_first_script

        generate_story_first_script(meta, paths, config, force=force)
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
        _guard_qa(
            "render", failed, checkpoint, paths,
            force_past_qa=force_past_qa, i_understand=True,
        )
        render_video(meta, paths, config, preview=preview, final=final, force=force)
        mark_stage(checkpoint, stage, paths)
    elif stage == PipelineStage.EXPORT:
        # Export publishes. The visual and audio gates can only be measured on the
        # finished file, so they cannot gate the render that produces it — but they must
        # gate the export that ships it, which is why this includes the render report.
        from manhwa2vid.video.qa_visual import upstream_failures

        _require_fresh_render_report(paths, force_past_qa=force_past_qa)
        failed = upstream_failures(project_dir, include_render=True)
        _guard_qa(
            "export", failed, checkpoint, paths,
            force_past_qa=force_past_qa, i_understand=i_understand,
        )
        export_youtube_pack(meta, paths, config)
        mark_stage(checkpoint, stage, paths)
    else:
        raise ValueError(f"Unknown stage: {stage}")


def _require_fresh_render_report(paths: dict[str, Path], *, force_past_qa: bool) -> None:
    """The render report must describe the video being packaged.

    Export reads `qa.render.json`, but a project directory holds dozens of previews and
    that report describes exactly one of them. Without this check, a clean report from an
    older render silently certifies a newer, unmeasured file.
    """
    report_path = paths["root"] / "qa.render.json"
    video = paths["output"] / "preview.mp4"
    final = paths["output"] / "final.mp4"
    if final.exists():
        video = final
    if not report_path.exists() or not video.exists():
        return  # nothing to contradict; the gate list handles a missing report

    from manhwa2vid.qa import QAGateFailure

    subject = (json.loads(report_path.read_text(encoding="utf-8")) or {}).get("subject") or {}
    if not subject:
        return  # written before subjects existed
    stat = video.stat()
    if subject.get("size") == stat.st_size:
        return
    message = (
        f"qa.render.json describes {subject.get('video')} ({subject.get('size')} bytes), "
        f"not the {video.name} being exported ({stat.st_size} bytes). "
        "Re-run `run render` so the gates measure what you are publishing."
    )
    if not force_past_qa:
        raise QAGateFailure(message)
    console.print(f"[red]{message}[/]")


def _guard_qa(
    stage: str,
    failed: list[str],
    checkpoint: Any,
    paths: dict[str, Path],
    *,
    force_past_qa: bool,
    i_understand: bool,
) -> None:
    """Refuse to proceed over failed gates, and RECORD it when someone insists.

    The override used to leave no trace: an in-memory flag, a console line, and the
    console scrolls away. Both audited videos shipped over failing gates and nothing in
    the project directory said so afterwards. Now every forced pass is written into the
    checkpoint, where `status` prints it in red forever.
    """
    if not failed:
        return

    from manhwa2vid.qa import QAGateFailure

    listing = "\n  ".join(failed)
    if not force_past_qa:
        raise QAGateFailure(
            f"Refusing to {stage} over failed QA gates:\n  {listing}\n"
            f"Fix them, or re-run with --force-past-qa"
            + (" --i-understand" if stage == "export" else "")
            + "."
        )
    if not i_understand:
        # Publishing is the irreversible one, so the flag alone is not enough: the
        # operator has to name what they are shipping over.
        raise QAGateFailure(
            f"--force-past-qa given, but {stage} publishes a video carrying these "
            f"failures:\n  {listing}\n"
            "Add --i-understand to proceed. It will be recorded in the checkpoint."
        )

    from datetime import datetime

    from manhwa2vid.models import QAOverride, save_json

    console.print(f"[red]FORCED {stage} over {len(failed)} failed gate(s):[/] {listing}")
    checkpoint.qa_overrides.append(
        QAOverride(
            stage=stage,
            at=datetime.now().isoformat(timespec="seconds"),
            failed_gates=list(failed),
        )
    )
    save_json(paths["checkpoint"], checkpoint)


def run_all_until_review(project_dir: Path, force: bool = False, force_past_qa: bool = False) -> None:
    """Run ingest through script generation, stopping before TTS."""
    stages = [
        PipelineStage.INGEST,
        PipelineStage.PANELS,
        PipelineStage.OCR,
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
