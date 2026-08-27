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
