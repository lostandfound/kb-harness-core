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
    """domain.content_root を絶対パスで返す。

    探索起点は start、無ければカレントディレクトリ、それでも見つからなければこのスクリプトの
    位置（ハーネス自身のチェックアウト）。相対パスを返すと cwd がリポジトリ直下でないとき
    別の場所を指すので、絶対パスに固定する。
    """
    candidates = [start] if start else [Path.cwd(), Path(__file__).resolve().parent.parent]
    last_error: ProjectError | None = None
    for search_start in candidates:
        try:
            project = Project.discover(search_start)
        except ProjectError as error:
            last_error = error
            continue
        return str(project.content_root)
    raise FileNotFoundError(str(last_error)) from last_error
