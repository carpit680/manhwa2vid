"""CLI entry point."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import typer
from rich.console import Console

from manhwa2vid.characters.seed import seed_series_bible
from manhwa2vid.config import find_repo_root, load_config
from manhwa2vid.ingest.images import discover_chapter_dirs
from manhwa2vid.models import ProjectMeta, SourceLanguage, SourceType, project_paths, save_json
from manhwa2vid.pipeline import init_glossary, load_project, run_all_until_review, run_stage
from manhwa2vid.models import PipelineStage
from manhwa2vid.review.checkpoints import approve_preview, approve_script, open_for_review
from manhwa2vid.script.lint import lint_beats
from manhwa2vid.video.render import latest_preview_path

app = typer.Typer(help="Manhwa recap video pipeline")
console = Console()

run_app = typer.Typer(help="Run pipeline stages")
review_app = typer.Typer(help="Review checkpoints")
app.add_typer(run_app, name="run")
app.add_typer(review_app, name="review")


def _slugify(title: str, chapters: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    ch = re.sub(r"[^a-z0-9]+", "-", chapters.lower()).strip("-")
    return f"{base}-ch{ch}"


@app.command("init")
def init_project(
    title: str = typer.Option(..., "--title", help="Manhwa title"),
    chapters: str = typer.Option(..., "--chapters", help='Chapter range e.g. "1-10" or "0-5"'),
    lang: SourceLanguage = typer.Option(SourceLanguage.KO, "--lang", help="Source language"),
    pdf: Path | None = typer.Option(None, "--pdf", exists=True, dir_okay=False, help="Source PDF path"),
    images: Path | None = typer.Option(
        None,
        "--images",
        exists=True,
        file_okay=False,
        dir_okay=True,
        help="Root folder of chapter image directories (or a single chapter folder)",
    ),
    project_dir: Path | None = typer.Option(None, "--project-dir", help="Override project directory"),
) -> None:
    """Create a new recap project from a PDF or image folder."""
    if bool(pdf) == bool(images):
        raise typer.BadParameter("Provide exactly one of --pdf or --images")

    root = find_repo_root()
    slug = _slugify(title, chapters)
    dest = project_dir or root / "projects" / slug
    if dest.exists():
        raise typer.BadParameter(f"Project already exists: {dest}")

    paths = project_paths(dest)
    for key in ("pages", "panels", "audio", "output", "debug"):
        paths[key].mkdir(parents=True, exist_ok=True)

    if pdf is not None:
        source_type = SourceType.PDF
        source_path = dest / "source.pdf"
        shutil.copy2(pdf, source_path)
        images_are_panels = False
    else:
        assert images is not None
        source_type = SourceType.IMAGES
        source_path = images.resolve()
        images_are_panels = True
        try:
            chapter_dirs = discover_chapter_dirs(source_path, chapters)
        except FileNotFoundError as exc:
            raise typer.BadParameter(str(exc)) from exc
        console.print(
            f"[dim]Found {len(chapter_dirs)} chapter folder(s) for range {chapters}[/]"
        )

    meta = ProjectMeta(
        slug=slug,
        title=title,
        chapters=chapters,
        source_lang=lang,
        source_type=source_type,
        source_path=str(source_path),
        pdf_path=str(source_path),
        images_are_panels=images_are_panels,
    )
    save_json(paths["meta"], meta)
    init_glossary(paths)
    seed_series_bible(meta, paths["glossary"], load_config())
    console.print(f"[green]Created project:[/] {dest}")
    if source_type == SourceType.IMAGES:
        console.print(f"[dim]Image source:[/] {source_path}")
    console.print(f"Next: manhwa2vid run all --project {dest}")


@run_app.command("all")
def run_all(
    project: Path = typer.Option(..., "--project", help="Project directory"),
    force: bool = typer.Option(False, "--force", help="Re-run completed stages"),
    force_past_qa: bool = typer.Option(False, "--force-past-qa", help="Continue despite failed QA gates"),
) -> None:
    """Run ingest → panels → OCR/scene → script (pauses for review)."""
    run_all_until_review(project.resolve(), force=force, force_past_qa=force_past_qa)


@run_app.command("ingest")
def run_ingest(project: Path = typer.Option(..., "--project"), force: bool = False) -> None:
    run_stage(project.resolve(), PipelineStage.INGEST, force=force)


@run_app.command("panels")
def run_panels(project: Path = typer.Option(..., "--project"), force: bool = False) -> None:
    run_stage(project.resolve(), PipelineStage.PANELS, force=force)


@run_app.command("ocr")
def run_ocr(
    project: Path = typer.Option(..., "--project"),
    force: bool = False,
    force_past_qa: bool = typer.Option(False, "--force-past-qa", help="Continue despite failed QA gates"),
) -> None:
    run_stage(project.resolve(), PipelineStage.OCR, force=force, force_past_qa=force_past_qa)



@run_app.command("script")
def run_script(
    project: Path = typer.Option(..., "--project"),
    force: bool = False,
    force_past_qa: bool = typer.Option(False, "--force-past-qa", help="Continue despite failed QA gates"),
) -> None:
    run_stage(
        project.resolve(),
        PipelineStage.SCRIPT,
        force=force,
        force_past_qa=force_past_qa,
    )


@run_app.command("tts")
def run_tts(project: Path = typer.Option(..., "--project"), force: bool = False) -> None:
    run_stage(project.resolve(), PipelineStage.TTS, force=force)


@run_app.command("render")
def run_render(
    project: Path = typer.Option(..., "--project"),
    preview: bool = typer.Option(True, "--preview/--no-preview"),
    final: bool = typer.Option(False, "--final", help="Render final 1080p output"),
    force: bool = False,
    # RENDER is the ONLY stage that refuses to run over a failed upstream gate, and it
    # was the only one missing this flag — so the QAGateFailure it raises told you to
    # re-run with an option `run render` did not accept. Dead end at exactly the moment
    # the operator has decided to override.
    force_past_qa: bool = typer.Option(False, "--force-past-qa", help="Continue despite failed QA gates"),
) -> None:
    run_stage(
        project.resolve(),
        PipelineStage.RENDER,
        preview=preview,
        final=final,
        force=force,
        force_past_qa=force_past_qa,
    )


@run_app.command("export")
def run_export(
    project: Path = typer.Option(..., "--project"),
    # Export PUBLISHES. The visual and audio gates can only be measured on the finished
    # file, so they gate here rather than at render — and forcing past them needs the
    # operator to say out loud what they are shipping over.
    force_past_qa: bool = typer.Option(False, "--force-past-qa", help="Continue despite failed QA gates"),
    i_understand: bool = typer.Option(
        False, "--i-understand",
        help="Required with --force-past-qa: confirms you are publishing over named failures",
    ),
) -> None:
    run_stage(
        project.resolve(), PipelineStage.EXPORT,
        force_past_qa=force_past_qa, i_understand=i_understand,
    )


@review_app.command("script")
def review_script_cmd(
    project: Path = typer.Option(..., "--project"),
    approve: bool = typer.Option(False, "--approve", help="Copy draft to final and mark approved"),
    lint: bool = typer.Option(False, "--lint", help="Report banned wording in script beats"),
    editor: bool = typer.Option(True, "--editor/--no-editor", help="Open draft in $EDITOR"),
) -> None:
    _, paths, config, checkpoint = load_project(project.resolve())
    draft = paths["script_draft"]
    if not draft.exists():
        raise typer.BadParameter("No script.draft.md — run script stage first.")
    if lint:
        from manhwa2vid.script.beats import load_script_beats

        beats = load_script_beats(paths).beats
        report = lint_beats(beats, config)
        if not report:
            console.print("[green]No banned wording found.[/]")
        else:
            for beat_id, hits in sorted(report.items()):
                console.print(f"  Beat {beat_id}: {', '.join(hits)}")
    if editor and not approve:
        open_for_review(draft)
    if approve:
        approve_script(paths, checkpoint)
        console.print(f"[green]Script approved:[/] {paths['script_final']}")


@review_app.command("preview")
def review_preview_cmd(
    project: Path = typer.Option(..., "--project"),
    approve: bool = typer.Option(False, "--approve"),
) -> None:
    _, paths, _, checkpoint = load_project(project.resolve())
    preview_path = latest_preview_path(paths["output"])
    if preview_path is None:
        raise typer.BadParameter("No preview found — run render --preview first.")
    console.print(f"Preview: {preview_path}")
    if approve:
        approve_preview(checkpoint, paths)
        console.print("[green]Preview approved. Run:[/] manhwa2vid run render --project ... --final")


@app.command("storyboard")
def storyboard_cmd(project: Path = typer.Option(..., "--project")) -> None:
    """Regenerate debug/storyboard.html from the current script (prefers script.final.md)."""
    from manhwa2vid.review.storyboard import write_storyboard
    from manhwa2vid.script.beats import _parse_markdown_beats, load_script_beats

    _, paths, _, _ = load_project(project.resolve())
    draft = load_script_beats(paths)
    if paths["script_final"].exists():
        draft.beats = _parse_markdown_beats(paths["script_final"])
    out = write_storyboard(paths, draft)
    console.print(f"[green]Storyboard written:[/] {out}")


@app.command("status")
def status(project: Path = typer.Option(..., "--project")) -> None:
    """Show project checkpoint status."""
    meta, paths, _, checkpoint = load_project(project.resolve())
    console.print(f"Source: {meta.source_type.value} → {meta.source_path}")
    console.print(f"Completed stages: {', '.join(s.value for s in checkpoint.completed_stages) or 'none'}")
    console.print(f"Script approved: {checkpoint.script_approved}")
    console.print(f"Preview approved: {checkpoint.preview_approved}")
    _print_gate_table(paths)
    _print_overrides(checkpoint)
    for name, path in paths.items():
        if path.suffix in (".json", ".md") and path.exists():
            console.print(f"  [green]✓[/] {name}: {path}")


def _print_gate_table(paths: dict[str, Path]) -> None:
    """Every gate, per stage. QA was invisible from `status` — the reports were on disk
    and nothing surfaced them, so a project could sit on a red gate indefinitely."""
    import json as _json

    from rich.table import Table

    from manhwa2vid.qa import CURRENT_QA_STAGES

    mark = {"pass": "[green]✓[/]", "warn": "[yellow]⚠[/]", "fail": "[red]✗[/]"}
    table = Table(title="QA gates", show_lines=False)
    table.add_column("stage"); table.add_column(""); table.add_column("gate")
    table.add_column("details", overflow="fold", max_width=70)

    rows = 0
    for stage in sorted(CURRENT_QA_STAGES):
        report = paths["root"] / f"qa.{stage}.json"
        if not report.exists():
            table.add_row(stage, "[dim]-[/]", "[dim]not run[/]", "")
            continue
        try:
            data = _json.loads(report.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            table.add_row(stage, "[red]![/]", "[red]unreadable report[/]", str(report))
            continue
        for gate in data.get("gates") or []:
            status_ = gate.get("status", "?")
            table.add_row(stage, mark.get(status_, "?"), gate.get("name", "?"),
                          (gate.get("details") or "").strip())
            rows += 1
    if rows:
        console.print(table)


def _print_overrides(checkpoint) -> None:
    """A forced pass is permanent and loud. It used to be a console line that scrolled
    away, which is how two videos shipped over failing gates with no record."""
    overrides = getattr(checkpoint, "qa_overrides", None) or []
    if not overrides:
        return
    console.print(f"\n[red bold]{len(overrides)} QA OVERRIDE(S) ON THIS PROJECT[/]")
    for entry in overrides:
        console.print(
            f"  [red]{entry.stage}[/] at {entry.at} over: {', '.join(entry.failed_gates)}"
        )


if __name__ == "__main__":
    app()
