"""述語の階層と標準述語。

述語は詳細度で三層に分けて扱う（docs/notes/jutsugo-kaisou-memo.md）。

- 層 0: `related-to`。未分類の印。方向も型制約も持たない。
- 層 1: `broader` を持たない述語。方向と domain / range を持ち、検証器に効く。
  ハーネスは名前・向き・意味を標準として文書で定め、型への束縛は導入先が決める。
- 層 2: `broader` で親に吊るした述語。意味の精緻化であり、導入先が任意で足す。

このモジュールは語彙ファイルの `broader` / `maps_to` を読み、階層の整合を検査し、
親の述語で問うたときに子孫のエッジも拾う汎化を提供する。推移閉包（`part-of` の多段）は
導かない。汎化は書かれたエッジを固定長の祖先列に写すだけで新しい事実を生まないが、
推移律は書かれていないエッジを導くからである。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

# 標準述語。名前と向きはハーネスが定め、domain / range は導入先が決める。
STANDARD_PREDICATES: Mapping[str, str] = {
    "part-of": "部分 → 全体",
    "derived-from": "派生物 → 起源",
    "created-by": "対象 → 主体",
    "located-in": "対象 → 場所",
}
UNCLASSIFIED_PREDICATE = "related-to"

VOCABULARY_PATH = "/vocabulary.yml"


@dataclass(frozen=True)
class Predicate:
    name: str
    description: str = ""
    domain: tuple[str, ...] = ()
    range: tuple[str, ...] = ()
    broader: Any = None
    maps_to: Any = None

    @property
    def constrained(self) -> bool:
        return bool(self.domain) and bool(self.range)


def _as_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(str(item) for item in value)
    return ()


def load_predicates(root: Path) -> dict[str, Predicate]:
    """`<content_root>/vocabulary.yml` の述語を、階層と標準対応のキーを含めて読む。

    `broader` / `maps_to` は形式検査のため生値のまま持つ。検査は validate_predicates が行う。
    """
    data = yaml.safe_load((root / "vocabulary.yml").read_text(encoding="utf-8")) or {}
    raw = data.get("predicates") or {}
    predicates: dict[str, Predicate] = {}
    for name, value in raw.items():
        if isinstance(value, dict):
            predicates[name] = Predicate(
                name=name,
                description=str(value.get("description", "") or ""),
                domain=_as_tuple(value.get("domain")),
                range=_as_tuple(value.get("range")),
                broader=value.get("broader"),
                maps_to=value.get("maps_to"),
            )
        else:
            predicates[name] = Predicate(name=name, description=str(value or ""))
    return predicates


def _parent(predicates: Mapping[str, Predicate], name: str) -> str | None:
    broader = predicates[name].broader
    return broader if isinstance(broader, str) and broader in predicates else None


def ancestors(predicates: Mapping[str, Predicate], name: str) -> list[str]:
    """親から根へ向かう祖先の列。循環があればそこで止める（検査は validate_predicates）。"""
    chain: list[str] = []
    seen = {name}
    current = _parent(predicates, name) if name in predicates else None
    while current is not None and current not in seen:
        chain.append(current)
        seen.add(current)
        current = _parent(predicates, current)
    return chain


def descendants(predicates: Mapping[str, Predicate], name: str) -> frozenset[str]:
    """自身を含む子孫の集合。親の述語で問うたときに拾うべきエッジの述語名。"""
    result = {name}
    for other in predicates:
        if other != name and name in ancestors(predicates, other):
            result.add(other)
    return frozenset(result)


def descendant_map(predicates: Mapping[str, Predicate]) -> dict[str, frozenset[str]]:
    return {name: descendants(predicates, name) for name in predicates}


def is_unclassified(name: str) -> bool:
    return name == UNCLASSIFIED_PREDICATE


def layer1_predicates(predicates: Mapping[str, Predicate]) -> list[str]:
    """層 1: `related-to` 以外で `broader` を持たない述語。"""
    return sorted(
        name for name, predicate in predicates.items()
        if not is_unclassified(name) and predicate.broader is None
    )


def nonstandard_layer1(predicates: Mapping[str, Predicate]) -> list[str]:
    """標準述語でない層 1 の述語。導入先が独自に層 1 を増やした状態を可視化するためのもの。"""
    return [name for name in layer1_predicates(predicates) if name not in STANDARD_PREDICATES]


def refinement_candidates(
    predicates: Mapping[str, Predicate], source_type: str | None, target_type: str | None
) -> list[str]:
    """`related-to` のエッジを精緻化できる層 1 の述語。

    domain と range の両方を持つ層 1 の述語のうち、始点と終点の型がともに収まるもの。
    無制約の述語は何にでも収まるので候補にしない。
    """
    if source_type is None or target_type is None:
        return []
    return [
        name for name in layer1_predicates(predicates)
        if predicates[name].constrained
        and source_type in predicates[name].domain
        and target_type in predicates[name].range
    ]


def validate_predicates(predicates: Mapping[str, Predicate]) -> list[str]:
    """`broader` / `maps_to` の整合を検査する。戻り値は `kb validate` の errors と同じ形式。"""
    errors: list[str] = []
    for name in sorted(predicates):
        predicate = predicates[name]
        broader = predicate.broader
        if broader is not None:
            if not isinstance(broader, str) or not broader:
                errors.append(f"ERROR {VOCABULARY_PATH}: predicates.{name}.broader は述語名の文字列でなければならない")
            elif broader == name:
                errors.append(f"ERROR {VOCABULARY_PATH}: predicates.{name}.broader が自身を指している")
            elif broader not in predicates:
                errors.append(f"ERROR {VOCABULARY_PATH}: predicates.{name}.broader に未知の述語 '{broader}'")
            else:
                chain = ancestors(predicates, name)
                if chain and _parent(predicates, chain[-1]) is not None:
                    errors.append(
                        f"ERROR {VOCABULARY_PATH}: predicates.{name}.broader が循環している"
                        f"（{' → '.join([name, *chain])}）"
                    )
                else:
                    parent = predicates[broader]
                    if parent.domain and not (predicate.domain and set(predicate.domain) <= set(parent.domain)):
                        errors.append(
                            f"ERROR {VOCABULARY_PATH}: predicates.{name}.domain は親 {broader} の domain の部分集合でなければならない"
                        )
                    if parent.range and not (predicate.range and set(predicate.range) <= set(parent.range)):
                        errors.append(
                            f"ERROR {VOCABULARY_PATH}: predicates.{name}.range は親 {broader} の range の部分集合でなければならない"
                        )
        maps_to = predicate.maps_to
        if maps_to is not None and (
            not isinstance(maps_to, list)
            or not maps_to
            or any(not isinstance(item, str) or not item.strip() for item in maps_to)
        ):
            errors.append(f"ERROR {VOCABULARY_PATH}: predicates.{name}.maps_to は空でない文字列のリストでなければならない")
    return errors


def export_predicates(predicates: Mapping[str, Predicate]) -> dict[str, dict[str, Any]]:
    """graph.json の `predicates` 要素。`broader` か `maps_to` を持つ述語だけを出す。

    汎化は消費側で行うので、階層はここで渡す。どちらも持たない語彙では空になり、
    render_graph はその場合 `predicates` キーを出さない（既存 KB の graph.json を変えない）。
    """
    exported: dict[str, dict[str, Any]] = {}
    for name in sorted(predicates):
        predicate = predicates[name]
        item: dict[str, Any] = {}
        if isinstance(predicate.broader, str) and predicate.broader in predicates and predicate.broader != name:
            item["broader"] = predicate.broader
        if isinstance(predicate.maps_to, list) and predicate.maps_to:
            item["maps_to"] = [str(entry) for entry in predicate.maps_to]
        if item:
            exported[name] = item
    return exported
