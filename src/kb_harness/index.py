"""Deterministic index generation."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Mapping

from .validation import _load_types, _parse_frontmatter


SECTION_HEADING = "## エンティティ一覧"
SECTION_RE = re.compile(
    r"(^## エンティティ一覧\n)(.*?)(?=^## |\Z)",
    re.MULTILINE | re.DOTALL,
)
COUNT_LINE_RE = re.compile(r"(\[[^\]]+\]\(/([^/]+)/index\.md\))（\d+件）")


def _entity_lines(dir_path: Path) -> str:
    entries: list[str] = []
    for path in sorted(dir_path.glob("*.md")):
        if path.name == "index.md":
            continue
        frontmatter, _body, error = _parse_frontmatter(path)
        if error or frontmatter is None:
            continue
        title = frontmatter.get("title", path.stem)
        description = frontmatter.get("description", "")
        separator = " — " if description else ""
        entries.append(
            f"- [{title}](/{dir_path.name}/{path.name}){separator}{description}\n"
        )
    return "".join(entries)


def _render_directory_index(dir_path: Path, text: str) -> str:
    listing = _entity_lines(dir_path)
    if SECTION_RE.search(text):
        # Keep the canonical blank line between the heading and its listing,
        # without introducing a second blank line at EOF.
        replacement = f"\n{listing}" if listing else "\n"
        return SECTION_RE.sub(
            lambda match: match.group(1) + replacement,
            text,
            count=1,
        )
    separator = "" if text.endswith("\n") else "\n"
    return f"{text}{separator}\n{SECTION_HEADING}\n\n{listing}"


def _render_root_index(root: Path, text: str) -> str:
    def replace_count(match: re.Match[str]) -> str:
        directory = root / match.group(2)
        if not directory.is_dir():
            return match.group(0)
        count = sum(
            1
            for path in directory.glob("*.md")
            if path.name != "index.md"
        )
        return f"{match.group(1)}（{count}件）"

    return COUNT_LINE_RE.sub(replace_count, text)


def plan_index(root: Path) -> dict[Path, str]:
    """Return deterministic index changes without writing them."""
    root = root.resolve()
    types = _load_types(root)
    candidates: dict[Path, str] = {}
    for definition in types.values():
        directory_name = definition.get("directory")
        if not isinstance(directory_name, str):
            continue
        index_path = root / directory_name / "index.md"
        if not index_path.is_file():
            continue
        current = index_path.read_text(encoding="utf-8")
        rendered = _render_directory_index(index_path.parent, current)
        if rendered != current:
            candidates[index_path] = rendered

    root_index = root / "index.md"
    if root_index.is_file():
        current = root_index.read_text(encoding="utf-8")
        rendered = _render_root_index(root, current)
        if rendered != current:
            candidates[root_index] = rendered

    return dict(sorted(candidates.items(), key=lambda item: str(item[0])))


def apply_changes(changes: Mapping[Path, str]) -> list[Path]:
    """Apply generated index changes using the shared atomic writer.

    The function remains as a compatibility API for callers of the Phase 1
    module.  All generated-file writers must go through the implementation in
    :mod:`kb_harness.sync`, so an individual ``index build`` has the same
    rollback guarantees as ``sync``.
    """
    # Import lazily because sync imports ``plan_index`` from this module.
    from .sync import apply_changes_atomically

    return apply_changes_atomically(changes)


def generate_index(root: Path) -> list[Path]:
    return apply_changes(plan_index(root))
