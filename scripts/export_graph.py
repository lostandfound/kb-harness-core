#!/usr/bin/env python3
"""Compatibility entry point for :mod:`kb_harness.graph`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 同じチェックアウトの src を pip で入った kb_harness より優先する。導入先で古い版が
# 入っていると、try/except の import は成功してしまい submodule の修正が効かない
_SRC = Path(__file__).resolve().parents[1] / "src"
if _SRC.is_dir():
    sys.path.insert(0, str(_SRC))
from kb_harness.graph import export_graph as _export_graph, render_graph
from kb_harness.project import Project
from kb_harness.sync import apply_changes_atomically, plan_graph
from kb_harness.validation import validate

def export_graph(root: Path, warnings: list[str] | None = None) -> dict:
    """Compatibility API that retains the legacy warning display behavior."""
    collected: list[str] = []
    graph = _export_graph(root, warnings=collected)
    if warnings is not None:
        warnings.extend(collected)
    for warning in collected:
        print(f"WARN {warning}", file=sys.stderr)
    return graph


__all__ = ["export_graph"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root")
    parser.add_argument("--out")
    parser.add_argument(
        "--force",
        action="store_true",
        help="validate() をスキップする（デバッグ用）",
    )
    args = parser.parse_args()
    root = Path(args.root) if args.root else Project.discover().content_root
    # views.root を設定した KB では graph.json に views 配列が入る。kb graph build と同じ出力にする
    try:
        views_root = Project.discover(root).views_root
    except Exception:
        views_root = None
    if not args.force:
        errors = validate(root)
        if errors:
            for error in errors:
                print(error, file=sys.stderr)
            raise SystemExit(1)
    warnings: list[str] = []
    export_graph(root, warnings=warnings)
    output = render_graph(root, views_root)
    if args.out:
        output_path = Path(args.out).resolve()
        # Keep the compatibility entry point on the same atomic writer as
        # ``kb graph build`` and ``kb sync``.
        apply_changes_atomically(plan_graph(root, output_path, views_root))
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
