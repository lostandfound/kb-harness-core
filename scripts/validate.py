#!/usr/bin/env python3
"""Compatibility entry point for :mod:`kb_harness.validation`."""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from kb_harness.validation import (
        _load_types,
        _parse_frontmatter,
        _url_reachable,
        check_urls,
        fix_timestamps,
        main,
        validate,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
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
