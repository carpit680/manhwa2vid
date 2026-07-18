"""Preview output path tests."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from manhwa2vid.video.render import latest_preview_path, preview_output_path


def test_preview_output_path_includes_timestamp() -> None:
    path = preview_output_path(Path("/tmp/out"), when=datetime(2025, 6, 30, 8, 53, 12))
    assert path.name == "preview_2025-06-30_085312.mp4"


def test_latest_preview_path_prefers_newest_dated() -> None:
    out = Path("/tmp/m2v_preview_test")
    out.mkdir(exist_ok=True)
    older = out / "preview_2025-06-29_120000.mp4"
    newer = out / "preview_2025-06-30_085312.mp4"
    older.write_bytes(b"x")
    newer.write_bytes(b"x")
    assert latest_preview_path(out) == newer
    older.unlink()
    newer.unlink()
    out.rmdir()
