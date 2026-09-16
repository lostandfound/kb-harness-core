"""Deterministic index generation."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Mapping

import yaml

from .validation import _load_types, _parse_frontmatter


SECTION_HEADING = "## エンティティ一覧"
SECTION_RE = re.compile(
    r"(^## エンティティ一覧\n)(.*?)(?=^## |\Z)",
    re.MULTILINE | re.DOTALL,
)
COUNT_LINE_RE = re.compile(r"(\[[^\]]+\]\(/([^/]+)/index\.md\))（\d+件）")
TAG_INDEX_START = "<!-- tag-index:start -->"
TAG_INDEX_END = "<!-- tag-index:end -->"
TAG_INDEX_HEADING = "## 分野別一覧"
TAG_INDEX_RE = re.compile(
    re.escape(TAG_INDEX_START) + r".*?" + re.escape(TAG_INDEX_END) + r"\n?",
    re.DOTALL,
)


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


def _vocabulary_tags(root: Path) -> list[str]:
    data = yaml.safe_load((root / "vocabulary.yml").read_text(encoding="utf-8")) or {}
    return [str(tag) for tag in (data.get("tags") or [])]


def render_tag_index(
    root: Path, types: Mapping[str, dict], tag_labels: Mapping[str, str] | None = None
) -> str:
    """vocabulary.yml の tags 順にタグ別一覧をマーカー付きで描画する。

    該当エンティティのないタグは省く。表示名は tag_labels に無ければタグ ID のまま。
    """
    labels = dict(tag_labels or {})
    entities: list[tuple[str, str, str, list[str]]] = []
    for type_name, definition in types.items():
        directory_name = definition.get("directory")
        if not isinstance(directory_name, str):
            continue
        directory = root / directory_name
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.md")):
            if path.name == "index.md":
                continue
            frontmatter, _body, error = _parse_frontmatter(path)
            if error or frontmatter is None:
                continue
            entities.append(
                (
                    f"/{directory_name}/{path.name}",
                    str(frontmatter.get("title", path.stem)),
                    type_name,
                    [str(tag) for tag in (frontmatter.get("tags") or [])],
                )
            )
    # 型の定義順に依存しないよう、パスで安定ソートする
    entities.sort(key=lambda item: item[0])

    lines = [TAG_INDEX_START, "", TAG_INDEX_HEADING, ""]
    for tag in _vocabulary_tags(root):
        hits = [entity for entity in entities if tag in entity[3]]
        if not hits:
            continue
        lines.append(f"### {labels.get(tag, tag)}（{len(hits)}件）")
        lines.append("")
        lines.extend(f"- [{title}]({href}) — {type_name}" for href, title, type_name, _ in hits)
        lines.append("")
    lines.append(TAG_INDEX_END)
    return "\n".join(lines) + "\n"


def _render_tag_section(text: str, block: str) -> str:
    """マーカー区間だけを置き換え、無ければ末尾に追記する。区間外は保持する。"""
    if TAG_INDEX_START in text and TAG_INDEX_END in text:
        return TAG_INDEX_RE.sub(lambda _match: block, text, count=1)
    return text.rstrip("\n") + "\n\n" + block


def plan_index(
    root: Path,
    *,
    by_tag: bool = False,
    tag_labels: Mapping[str, str] | None = None,
) -> dict[Path, str]:
    """Return deterministic index changes without writing them.

    ``by_tag`` が真のときはルート ``index.md`` のタグ別一覧区間も対象にする。
    """
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
        if by_tag:
            rendered = _render_tag_section(rendered, render_tag_index(root, types, tag_labels))
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
    from .sync import execute_write_plan, plan_write

    return execute_write_plan(plan_write(changes))


def generate_index(root: Path) -> list[Path]:
    return apply_changes(plan_index(root))
