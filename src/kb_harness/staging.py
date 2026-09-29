"""Private helpers for validating prospective KB writes in isolation."""

from __future__ import annotations

import dataclasses
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable

from .concerns import plan_concerns_index, validate_concerns
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
        # views / concerns は content_root の外に置けるので、graph.json の views 要素と各一覧を
        # 一時 KB で再現するには定義ディレクトリも写す必要がある
        staged_views_root, staged_views_index = _stage_generated_section(
            getattr(project, "views_root", None), getattr(project, "views_index", None), repo_root, stage_root, copytree
        )
        staged_concerns_root, staged_concerns_index = _stage_generated_section(
            getattr(project, "concerns_root", None), getattr(project, "concerns_index", None), repo_root, stage_root, copytree
        )

        staged_path = stage_content / relative
        staged_path.parent.mkdir(parents=True, exist_ok=True)
        staged_path.write_text(proposed_text, encoding="utf-8")
        # ビュー定義の不備は派生物の生成（export_views）で ViewError になって先に落ちるので、
        # 生成の前に検査して他の検証エラーと同じ形で返す
        if staged_views_root is not None:
            view_errors = validate_views(stage_content, staged_views_root)
            if view_errors:
                raise validation_error("; ".join(view_errors))
        if staged_concerns_root is not None:
            concern_errors = validate_concerns(stage_content, staged_concerns_root)
            if concern_errors:
                raise validation_error("; ".join(concern_errors))
        # index.by_tag などの設定を引き継がないと、作成直後の sync --check が陳腐化を報告する
        staged_project = dataclasses.replace(
            project,
            repo_root=stage_root,
            content_root=stage_content,
            views_root=staged_views_root,
            views_index=staged_views_index,
            concerns_root=staged_concerns_root,
            concerns_index=staged_concerns_index,
        )
        derived = {
            **plan_index(
                stage_content,
                by_tag=getattr(project, "index_by_tag", False),
                tag_labels=getattr(project, "tag_labels", None),
            ),
            **plan_graph(stage_content, stage_root / "graph.json", staged_views_root),
            **plan_views_index(stage_content, staged_views_root, staged_views_index),
            **plan_concerns_index(stage_content, staged_concerns_root, staged_concerns_index),
        }
        execute_write_plan(plan_write(derived))
        errors = validate(stage_content, repo_root=stage_root)
        if errors:
            raise validation_error("; ".join(errors))
        if plan_sync(staged_project):
            raise sync_error()

        changes = {proposed_path: proposed_text}
        for staged in derived:
            real = repo_root / staged.relative_to(stage_root)
            changes[real] = staged.read_text(encoding="utf-8")
        return changes


def _stage_generated_section(
    root: Path | None,
    index: Path | None,
    repo_root: Path,
    stage_root: Path,
    copytree: Callable[..., Any],
) -> tuple[Path | None, Path | None]:
    """定義ディレクトリと生成済み一覧を一時 KB へ写し、写し先のパスを返す。未設定なら (None, None)。"""
    if root is None or index is None:
        return None, None
    staged_root = stage_root / root.resolve().relative_to(repo_root)
    staged_index = stage_root / index.resolve().relative_to(repo_root)
    # root が content_root を含む配置（content_root: kb/entities, views.root: kb）では
    # 写し先が content のコピーで既にできている。存在で飛ばすと定義が写らない
    if root.is_dir():
        copytree(root, staged_root, symlinks=True, dirs_exist_ok=True)
    if index.is_file():
        staged_index.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(index, staged_index)
    return staged_root, staged_index
