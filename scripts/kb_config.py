"""Compatibility helpers for locating the configured KB content root."""

from __future__ import annotations

import sys
from pathlib import Path

# 同じチェックアウトの src を pip で入った kb_harness より優先する。導入先で古い版が
# 入っていると、try/except の import は成功してしまい submodule の修正が効かない
_SRC = Path(__file__).resolve().parents[1] / "src"
if _SRC.is_dir():
    sys.path.insert(0, str(_SRC))
from kb_harness.project import Project, ProjectError


def default_content_root(start: Path | None = None) -> str:
    """Return domain.content_root, preserving the legacy relative-path API."""
    search_start = start or Path(__file__).resolve().parent.parent
    try:
        project = Project.discover(search_start)
    except ProjectError as error:
        raise FileNotFoundError(str(error)) from error
    return str(project.content_root.relative_to(project.repo_root))
