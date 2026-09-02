"""Environment and project health checks."""

from __future__ import annotations

import importlib.metadata
import tomllib
from pathlib import Path

from . import __version__
from .project import Project
from .sync import plan_sync


def _ontology_version() -> str:
    try:
        return importlib.metadata.version("kb-ontology-core")
    except importlib.metadata.PackageNotFoundError:
        sibling = Path(__file__).resolve().parents[3] / "kb-ontology-core" / "pyproject.toml"
        if sibling.is_file():
            data = tomllib.loads(sibling.read_text(encoding="utf-8"))
            return str(data["project"]["version"])
        return "unknown"


def diagnose(project: Project) -> tuple[dict[str, str], list[dict[str, str]]]:
    details = {
        "kb_harness_version": __version__,
        "kb_ontology_core_version": _ontology_version(),
        "repo_root": str(project.repo_root),
        "content_root": str(project.content_root),
    }
    diagnostics: list[dict[str, str]] = []
    if not project.content_root.is_dir():
        diagnostics.append(
            {
                "code": "doctor.content_root_missing",
                "message": f"content root does not exist: {project.content_root}",
            }
        )
        return details, diagnostics
    vocabulary = project.content_root / "vocabulary.yml"
    if not vocabulary.is_file():
        diagnostics.append(
            {
                "code": "doctor.vocabulary_missing",
                "message": f"vocabulary does not exist: {vocabulary}",
            }
        )
        return details, diagnostics
    for path in plan_sync(project):
        relative = str(path.relative_to(project.repo_root))
        diagnostics.append(
            {
                "code": "doctor.generated_stale",
                "message": f"generated file is stale: {relative}",
                "path": relative,
            }
        )
    return details, diagnostics
