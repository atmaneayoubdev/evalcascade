"""Locate the built dashboard (Next.js static export)."""

from __future__ import annotations

import os
from pathlib import Path

PACKAGED_DIR = Path(__file__).resolve().parent.parent / "dashboard_dist"


def find_dashboard() -> Path | None:
    """First existing dashboard bundle among: $EVALCASCADE_DASHBOARD_DIR, the packaged copy,
    ``./web/out`` and the repository's ``web/out`` (editable installs)."""
    candidates: list[Path] = []
    if os.environ.get("EVALCASCADE_DASHBOARD_DIR"):
        candidates.append(Path(os.environ["EVALCASCADE_DASHBOARD_DIR"]))
    candidates += [
        PACKAGED_DIR,
        Path.cwd() / "web" / "out",
        Path(__file__).resolve().parents[3] / "web" / "out",
    ]
    for path in candidates:
        if (path / "index.html").is_file():
            return path.resolve()
    return None
