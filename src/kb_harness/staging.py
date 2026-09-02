"""Private helpers for validating prospective KB writes in isolation."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable

from .graph import plan_graph
from .index import plan_index
from .sync import execute_write_plan, plan_sync, plan_write
from .validation import validate


def stage_and_validate(
    project: Any,
    proposed_path: Path,
    proposed_text: str,
    *,
    prefix: str,
    validation_error: Callable[[str], Exception],
    sync_error: Callable[[], Exception],
    containment_error: Callable[[Path], Exception] | None = None,
    copytree: Callable[..., Any] = shutil.copytree,
) -> dict[Path, str]:
    """Build derived files and validate a proposed document without real writes."""
    with tempfile.TemporaryDirectory(prefix=prefix) as tempdir:
        stage_root = (Path(tempdir) / "repo").resolve()
        repo_root = project.repo_root.resolve()
        content_root = project.content_root.resolve()
        try:
            relative = proposed_path.resolve().relative_to(content_root)
        except ValueError as error:
            exc = (containment_error or (lambda path: validation_error(f"path must be inside content root: {path}")))(proposed_path)
            raise exc from error

        stage_content = stage_root / content_root.relative_to(repo_root)
        copytree(content_root, stage_content, symlinks=True)
        for name in ("kb-domain.yml", "graph.json"):
            source = repo_root / name
            if source.is_file():
                stage_root.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, stage_root / name)
        evals = repo_root / "evals"
        if evals.is_dir():
            copytree(evals, stage_root / "evals", symlinks=True)

        staged_path = stage_content / relative
        staged_path.parent.mkdir(parents=True, exist_ok=True)
        staged_path.write_text(proposed_text, encoding="utf-8")
        staged_project = type(project)(repo_root=stage_root, content_root=stage_content)
        derived = {**plan_index(stage_content), **plan_graph(stage_content, stage_root / "graph.json")}
        execute_write_plan(plan_write(derived))
        errors = validate(stage_content)
        if errors:
            raise validation_error("; ".join(errors))
        if plan_sync(staged_project):
            raise sync_error()

        changes = {proposed_path: proposed_text}
        for staged in derived:
            real = repo_root / staged.relative_to(stage_root)
            changes[real] = staged.read_text(encoding="utf-8")
        return changes
