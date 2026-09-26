"""vocabulary.yml の types: セクションの読み込みと宣言の検査。

validation（kb validate）と entity（kb entity create / new_entity.py）の両方が
同じ規則で型定義を読むための共有層。ここに規則を置き、二重に持たない。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

TYPE_KEYS = ("directory", "extra_fields", "optional_fields", "graph", "sections", "sources_required")


def load_types(root: Path) -> dict[str, dict[str, Any]]:
    """types: を読み、型名 → {directory, extra_fields, optional_fields, graph, sections, sources_required} を返す。

    types: が無ければ空の辞書を返す。必須かどうかは呼び手が決める。
    """
    data = yaml.safe_load((root / "vocabulary.yml").read_text(encoding="utf-8")) or {}
    raw_types = data.get("types") if isinstance(data, dict) else None
    if not isinstance(raw_types, dict):
        return {}
    types: dict[str, dict[str, Any]] = {}
    for name, definition in raw_types.items():
        if not isinstance(name, str):
            continue
        definition = definition if isinstance(definition, dict) else {}
        types[name] = {
            "directory": definition.get("directory"),
            "extra_fields": definition.get("extra_fields") or [],
            "optional_fields": definition.get("optional_fields") or [],
            "graph": definition.get("graph", True),
            "sections": definition.get("sections") or [],
            "sources_required": definition.get("sources_required", True),
        }
    return types


def validate_type_fields(types: dict[str, dict[str, Any]]) -> list[str]:
    """extra_fields / optional_fields の宣言そのものを検査し、問題を文字列で返す。

    不正な宣言は空のリストに置き換える。以降のエンティティ検査が壊れた宣言を読まないため。
    """
    problems: list[str] = []
    for name, type_def in types.items():
        lists: dict[str, list[str]] = {}
        for key in ("extra_fields", "optional_fields"):
            value = type_def.get(key) or []
            if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
                problems.append(f"types.{name}.{key} はフィールド名のリストでなければならない")
                value = []
                type_def[key] = value
            lists[key] = value
        overlap = sorted(set(lists["extra_fields"]) & set(lists["optional_fields"]))
        if overlap:
            problems.append(
                f"types.{name} で extra_fields と optional_fields に同じフィールドがある: " + ", ".join(overlap)
            )
    return problems
