"""Environment and project health checks."""

from __future__ import annotations

import importlib.metadata
import importlib
import re
from typing import Any
from pathlib import Path

from . import __version__
from .project import Project
from .sync import plan_sync

_CORE_APIS = (
    "Diagnostic",
    "Ontology",
    "export_claim",
    "plan_transition",
    "validate_claim",
)
_CORE_PACKAGE = "kb-ontology-core"


def _metadata_version(package: str) -> str | None:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return None


def _ontology_version() -> str:
    version = _metadata_version(_CORE_PACKAGE)
    return version if version is not None else "unknown"


def _dependency_requirement() -> str | None:
    """Return the declared ontology-core requirement, if harness metadata exists."""
    try:
        requirements = importlib.metadata.requires("kb-harness-core") or []
    except importlib.metadata.PackageNotFoundError:
        return None
    for requirement in requirements:
        if requirement.split(";")[0].strip().lower().startswith(_CORE_PACKAGE):
            return requirement
    return ""


def _declared_version(requirement: str) -> str | None:
    """Extract a pinned version or git tag without resolving anything remotely."""
    direct_ref = re.search(r"@v?(\d+\.\d+\.\d+)(?:$|[\s;#])", requirement)
    if direct_ref:
        return direct_ref.group(1)
    pinned = re.search(r"(?:===|==|~=|>=)\s*v?(\d+\.\d+\.\d+)", requirement)
    return pinned.group(1) if pinned else None


def _diagnostic(code: str, message: str, *, field: str | None = None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"code": code, "message": message}
    if field is not None:
        result["field"] = field
    if context is not None:
        result["context"] = context
    return result


def _core_diagnostics() -> list[dict[str, Any]]:
    """Check the installed core distribution and its public API, read-only."""
    core_version = _metadata_version(_CORE_PACKAGE)
    # A source-only checkout has no distribution metadata.  Its existing
    # project checks remain useful, but cannot claim an installed dependency.
    if core_version is None and _dependency_requirement() is None:
        return []

    diagnostics: list[dict[str, Any]] = []
    try:
        core = importlib.import_module("kb_ontology_core")
    except Exception as error:
        return [
            _diagnostic(
                "doctor.ontology.import_failed",
                f"cannot import {_CORE_PACKAGE}: {type(error).__name__}: {error}",
                context={"package": _CORE_PACKAGE},
            )
        ]

    for name in _CORE_APIS:
        api = getattr(core, name, None)
        if not callable(api):
            diagnostics.append(
                _diagnostic(
                    "doctor.ontology.api_missing",
                    f"{_CORE_PACKAGE} is missing required API '{name}'",
                    field=name,
                    context={"package": _CORE_PACKAGE, "required": True},
                )
            )
    requirement = _dependency_requirement()
    if requirement is not None and not requirement:
        diagnostics.append(
            _diagnostic(
                "doctor.ontology.dependency_missing",
                f"kb-harness-core does not declare a dependency on {_CORE_PACKAGE}",
                field="dependencies",
                context={"package": _CORE_PACKAGE},
            )
        )
    elif requirement:
        declared = _declared_version(requirement)
        if declared is None:
            diagnostics.append(
                _diagnostic(
                    "doctor.ontology.dependency_unpinned",
                    f"{_CORE_PACKAGE} dependency has no version or tag pin",
                    field="dependencies",
                    context={"requirement": requirement},
                )
            )
        elif core_version is None:
            diagnostics.append(
                _diagnostic(
                    "doctor.ontology.metadata_missing",
                    f"installed {_CORE_PACKAGE} has no package metadata",
                    context={"required_version": declared},
                )
            )
        elif core_version != declared:
            diagnostics.append(
                _diagnostic(
                    "doctor.ontology.version_mismatch",
                    f"declared {_CORE_PACKAGE} version {declared} does not match installed {core_version}",
                    field="version",
                    context={"declared": declared, "installed": core_version},
                )
            )
    return diagnostics


def diagnose(project: Project) -> tuple[dict[str, str], list[dict[str, Any]]]:
    details = {
        "kb_harness_version": __version__,
        "kb_ontology_core_version": _ontology_version(),
        "repo_root": str(project.repo_root),
        "content_root": str(project.content_root),
    }
    diagnostics: list[dict[str, Any]] = _core_diagnostics()
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
