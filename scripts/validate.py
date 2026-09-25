#!/usr/bin/env python3
"""Compatibility entry point for :mod:`kb_harness.validation`."""

from __future__ import annotations

import sys
from pathlib import Path

# 同じチェックアウトの src を pip で入った kb_harness より優先する。導入先で古い版が
# 入っていると、try/except の import は成功してしまい submodule の修正が効かない
_SRC = Path(__file__).resolve().parents[1] / "src"
if _SRC.is_dir():
    sys.path.insert(0, str(_SRC))
from kb_harness.validation import (
    _load_types,
    _parse_frontmatter,
    _url_reachable,
    check_urls,
    fix_timestamps,
    main,
    validate,
)

__all__ = [
    "_load_types",
    "_parse_frontmatter",
    "_url_reachable",
    "check_urls",
    "fix_timestamps",
    "main",
    "validate",
]


if __name__ == "__main__":
    main()
