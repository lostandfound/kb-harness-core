"""vocabulary.yml の名前の文字種を検査する。

規則（docs/configuration.md「名前の文字種」が正本）:
- 型名は PascalCase（`Person` / `HistoricalEvent`）
- 述語名は kebab-case（`part-of` / `created-by`）
- フィールド名は snake_case（`born` / `same_as`）
- プロパティ名（値 Claim の `property`）は述語と同じ slot に立つので kebab-case（`established-year`）
- タグは kebab-case（`cs` / `machine-learning`）
いずれも ASCII。slug・ファイル名・ref ID の kebab-case は既存の検査が別に見る。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

import yaml

PASCAL_CASE_RE = re.compile(r"^[A-Z][A-Za-z0-9]*$")
KEBAB_CASE_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SNAKE_CASE_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")

_RULES = (
    ("types", PASCAL_CASE_RE, "型名は PascalCase（例 Person / HistoricalEvent）"),
    ("predicates", KEBAB_CASE_RE, "述語名は kebab-case（例 part-of / created-by）"),
    ("properties", KEBAB_CASE_RE, "プロパティ名は述語と同じく kebab-case（例 established-year）"),
)


def validate_vocabulary_names(data: Mapping[str, Any]) -> list[str]:
    """vocabulary.yml の内容から、名前の文字種の違反を文字列で返す。"""
    problems: list[str] = []
    for section, pattern, rule in _RULES:
        entries = data.get(section)
        if not isinstance(entries, Mapping):
            continue
        for name in entries:
            if not isinstance(name, str) or not pattern.match(name):
                problems.append(f"{section}.{name!s} の名前が規則に合わない。{rule}")
    types = data.get("types")
    if isinstance(types, Mapping):
        for type_name, definition in types.items():
            if not isinstance(definition, Mapping):
                continue
            for key in ("extra_fields", "optional_fields"):
                fields = definition.get(key)
                if not isinstance(fields, list):
                    continue
                for field in fields:
                    if isinstance(field, str) and field and not SNAKE_CASE_RE.match(field):
                        problems.append(
                            f"types.{type_name}.{key} の '{field}' が規則に合わない。フィールド名は snake_case（例 born / same_as）"
                        )
    tags = data.get("tags")
    if isinstance(tags, list):
        for tag in tags:
            if isinstance(tag, str) and not KEBAB_CASE_RE.match(tag):
                problems.append(f"tags の '{tag}' が規則に合わない。タグは kebab-case（例 cs / machine-learning）")
    return problems


def validate_vocabulary_names_at(root: Path) -> list[str]:
    data = yaml.safe_load((root / "vocabulary.yml").read_text(encoding="utf-8")) or {}
    return validate_vocabulary_names(data) if isinstance(data, Mapping) else []
