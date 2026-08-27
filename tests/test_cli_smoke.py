"""The CLI had zero tests across 15 commands.

These do not exercise pipeline behaviour — they check that the command surface still
exists, still parses, and that retired subcommands are gone rather than crashing. A
deleted stage that leaves its subcommand behind fails at runtime with a traceback
instead of a usage error.
"""

from __future__ import annotations

from typer.testing import CliRunner

from manhwa2vid.cli import app

runner = CliRunner()

LIVE = ["ingest", "panels", "ocr", "script", "tts", "render", "export"]
RETIRED = ["story", "scout", "cast"]


def test_help_lists_the_command_groups():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for group in ("init", "run", "review", "status", "storyboard"):
        assert group in result.output


def test_every_live_stage_has_a_run_subcommand():
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    for stage in LIVE:
        assert stage in result.output, f"`run {stage}` is missing"


def test_retired_stages_are_gone_from_the_cli():
    """They must not linger as commands that explode on a deleted import."""
    listed = runner.invoke(app, ["run", "--help"]).output
    for stage in RETIRED:
        assert f"\n  {stage}" not in listed
        result = runner.invoke(app, ["run", stage, "--project", "."])
        assert result.exit_code != 0
        assert "No module named" not in str(result.output)


def test_commands_require_a_project():
    for cmd in (["run", "script"], ["review", "script"], ["status"]):
        result = runner.invoke(app, cmd)
        assert result.exit_code != 0, f"{cmd} ran without --project"


def test_unknown_project_is_a_clean_error_not_a_traceback():
    result = runner.invoke(app, ["status", "--project", "/nonexistent/project"])
    assert result.exit_code != 0
    assert "Traceback" not in result.output


def test_every_stage_that_can_raise_qagatefailure_accepts_force_past_qa():
    """The override named in the error message must exist on the command that raises it.

    `run render` is the only stage that refuses over a failed UPSTREAM gate, and it
    shipped without `--force-past-qa` while the QAGateFailure it raises said to "re-run
    with --force-past-qa" — an instruction the CLI rejected. Introspects the command's
    parameters rather than its --help text: rich wraps help output and injects ANSI
    mid-word, so a substring search there passes and fails for the wrong reasons.
    """
    import inspect
    import re

    import typer.main

    from manhwa2vid import pipeline
    from manhwa2vid.cli import run_app

    # Which stages does run_stage refuse to run over a failed upstream gate? Split its
    # source on the stage branches and keep the ones whose body consults force_past_qa.
    src = inspect.getsource(pipeline.run_stage)
    blocks = re.split(r"\n    (?:el)?if stage == PipelineStage\.", src)[1:]
    gated = {b.split(":", 1)[0].strip().lower() for b in blocks if "force_past_qa" in b}
    assert "render" in gated, "run_stage no longer gates RENDER — update this test"

    group = typer.main.get_group(run_app)
    for stage in sorted(gated):
        opts = {o for p in group.commands[stage].params for o in p.opts}
        assert "--force-past-qa" in opts, f"`run {stage}` raises QAGateFailure but has no override"
