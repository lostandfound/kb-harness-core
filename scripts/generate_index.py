#!/usr/bin/env python3
"""Compatibility entry point for :mod:`kb_harness.index`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from kb_harness.index import generate_index as _generate_index
    from kb_harness.project import Project
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from kb_harness.index import generate_index as _generate_index
    from kb_harness.project import Project

def generate_index(root: Path) -> list[Path]:
    """Compatibility wrapper preserving the caller's lexical root paths."""
    root_path = Path(root)
    changed = _generate_index(root_path)
    resolved_root = root_path.resolve()
    return [root_path / path.relative_to(resolved_root) for path in changed]


__all__ = ["generate_index"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root")
    args = parser.parse_args()
    root = Path(args.root) if args.root else Project.discover().content_root
    generate_index(root)


if __name__ == "__main__":
    main()
