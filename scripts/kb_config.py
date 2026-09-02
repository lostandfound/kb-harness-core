"""Compatibility helpers for locating the configured KB content root."""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from kb_harness.project import Project, ProjectError
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from kb_harness.project import Project, ProjectError


def default_content_root(start: Path | None = None) -> str:
    """Return domain.content_root, preserving the legacy relative-path API."""
    search_start = start or Path(__file__).resolve().parent.parent
    try:
        project = Project.discover(search_start)
    except ProjectError as error:
        raise FileNotFoundError(str(error)) from error
    return str(project.content_root.relative_to(project.repo_root))
