"""Private helpers for validating prospective KB writes in isolation."""

from __future__ import annotations

import dataclasses
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable

from .graph import plan_graph
from .index import plan_index
from .sync import execute_write_plan, plan_sync, plan_write
from .validation import validate
from .views import plan_views_index, validate_views


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
        # views は content_root の外に置けるので、graph.json の views 要素とビュー一覧を
        # 一時 KB で再現するには定義ディレクトリも写す必要がある
        views_root = getattr(project, "views_root", None)
        views_index = getattr(project, "views_index", None)
        staged_views_root = None
        staged_views_index = None
        if views_root is not None and views_index is not None:
            staged_views_root = stage_root / views_root.resolve().relative_to(repo_root)
            staged_views_index = stage_root / views_index.resolve().relative_to(repo_root)
            if views_root.is_dir():
                copytree(views_root, staged_views_root, symlinks=True)
            if views_index.is_file():
                staged_views_index.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(views_index, staged_views_index)

        staged_path = stage_content / relative
        staged_path.parent.mkdir(parents=True, exist_ok=True)
        staged_path.write_text(proposed_text, encoding="utf-8")
        # index.by_tag などの設定を引き継がないと、作成直後の sync --check が陳腐化を報告する
        staged_project = dataclasses.replace(
            project,
            repo_root=stage_root,
            content_root=stage_content,
            views_root=staged_views_root,
            views_index=staged_views_index,
        )
        derived = {
            **plan_index(
                stage_content,
                by_tag=getattr(project, "index_by_tag", False),
                tag_labels=getattr(project, "tag_labels", None),
            ),
            **plan_graph(stage_content, stage_root / "graph.json", staged_views_root),
            **plan_views_index(stage_content, staged_views_root, staged_views_index),
        }
        execute_write_plan(plan_write(derived))
        errors = validate(stage_content)
        if staged_views_root is not None:
            errors.extend(validate_views(stage_content, staged_views_root))
        if errors:
            raise validation_error("; ".join(errors))
        if plan_sync(staged_project):
            raise sync_error()

        changes = {proposed_path: proposed_text}
        for staged in derived:
            real = repo_root / staged.relative_to(stage_root)
            changes[real] = staged.read_text(encoding="utf-8")
        return changes
