"""述語の階層と標準述語。

述語は詳細度で三層に分けて扱う（docs/notes/jutsugo-kaisou-memo.md）。

- 層 0: `related-to`。未分類の印。方向も意味も持たず、階層に属さない（親にも子にもならない）。
  domain / range は書けば通常どおり検査するが、それは型の粗い制限であって層 1 の資格ではない。
- 層 1: `broader` を持たない述語。方向と domain / range を持ち、検証器に効く。
  ハーネスは名前・向き・意味を標準として文書で定め、型への束縛は導入先が決める。
- 層 2: `broader` で層 1 以下の親に吊るした述語。意味の精緻化であり、導入先が任意で足す。

このモジュールは語彙ファイルの述語を唯一の正規化器として読み（validation._load_vocabulary も
ここを経由する）、階層の整合を検査し、親の述語で問うたときに子孫のエッジも拾う汎化を提供する。
推移閉包（`part-of` の多段）は導かない。汎化は書かれたエッジを固定長の祖先列に写すだけで
新しい事実を生まないが、推移律は書かれていないエッジを導くからである。
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
    "follows": "後続 → 先行",
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
    # domain / range が YAML でリスト以外（スカラー等）だったキー。検査で ERROR にする
    malformed: tuple[str, ...] = ()

    @property
    def constrained(self) -> bool:
        return bool(self.domain) and bool(self.range)


def _type_list(value: Any) -> tuple[tuple[str, ...], bool]:
    """domain / range の値を型名の組に正規化する。戻り値の第 2 要素は形式が正しいか。

    スカラー文字列は 1 要素として扱う（無制約に化けさせない）が、形式違反として報告する。
    """
    if value is None:
        return (), True
    if isinstance(value, list):
        return tuple(str(item) for item in value), all(isinstance(item, str) and item for item in value)
    if isinstance(value, str) and value:
        return (value,), False
    return (), False


def predicates_from_mapping(raw: Mapping[str, Any] | None) -> dict[str, Predicate]:
    """`vocabulary.yml` の `predicates` を Predicate に正規化する。語彙の述語はすべてここを通す。"""
    predicates: dict[str, Predicate] = {}
    for name, value in (raw or {}).items():
        if isinstance(value, dict):
            domain, domain_ok = _type_list(value.get("domain"))
            range_, range_ok = _type_list(value.get("range"))
            malformed = tuple(key for key, ok in (("domain", domain_ok), ("range", range_ok)) if not ok)
            predicates[name] = Predicate(
                name=name,
                description=str(value.get("description", "") or ""),
                domain=domain,
                range=range_,
                broader=value.get("broader"),
                maps_to=value.get("maps_to"),
                malformed=malformed,
            )
        else:
            predicates[name] = Predicate(name=name, description=str(value or ""))
    return predicates


def load_predicates(root: Path) -> dict[str, Predicate]:
    """`<content_root>/vocabulary.yml` の述語を読む。"""
    data = yaml.safe_load((root / "vocabulary.yml").read_text(encoding="utf-8")) or {}
    return predicates_from_mapping(data.get("predicates"))


def as_mapping(predicates: Mapping[str, Predicate]) -> dict[str, dict[str, Any]]:
    """kb-ontology-core の Ontology.from_mapping に渡す形（description / domain / range）。"""
    return {
        name: {"description": predicate.description, "domain": list(predicate.domain), "range": list(predicate.range)}
        for name, predicate in predicates.items()
    }


def _parent(predicates: Mapping[str, Predicate], name: str) -> str | None:
    # 層 0 は階層に属さない。related-to 自身の broader も、related-to を指す broader も親にしない
    if is_unclassified(name):
        return None
    broader = predicates[name].broader
    if isinstance(broader, str) and broader in predicates and broader != name and not is_unclassified(broader):
        return broader
    return None


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


def _cycles(predicates: Mapping[str, Predicate]) -> list[list[str]]:
    """broader が作る循環を、循環上のノードだけで列挙する。各循環は最小の名前から始める。"""
    cycles: list[list[str]] = []
    reported: set[str] = set()
    for name in sorted(predicates):
        if name in reported:
            continue
        path: list[str] = []
        current: str | None = name
        while current is not None and current not in path:
            path.append(current)
            current = _parent(predicates, current)
        if current is None or current in reported:
            continue
        cycle = path[path.index(current):]
        start = cycle.index(min(cycle))
        cycle = cycle[start:] + cycle[:start]
        cycles.append(cycle)
        reported.update(cycle)
    return cycles


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
    """層 1: `related-to` 以外で、有効な親（related-to 以外の実在する述語）を持たない述語。"""
    return sorted(
        name for name in predicates
        if not is_unclassified(name) and _parent(predicates, name) is None
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
    """述語定義の形式と `broader` / `maps_to` の整合を検査する。戻り値は `kb validate` の errors と同じ形式。"""
    errors: list[str] = []
    for cycle in _cycles(predicates):
        errors.append(
            f"ERROR {VOCABULARY_PATH}: predicates の broader が循環している（{' → '.join([*cycle, cycle[0]])}）"
        )
    for name in sorted(predicates):
        predicate = predicates[name]
        for key in predicate.malformed:
            errors.append(f"ERROR {VOCABULARY_PATH}: predicates.{name}.{key} は型名のリストでなければならない")
        broader = predicate.broader
        if broader is not None:
            if is_unclassified(name):
                errors.append(
                    f"ERROR {VOCABULARY_PATH}: predicates.{name} に broader は書けない（未分類の印であり、階層に属さない）"
                )
            elif not isinstance(broader, str) or not broader:
                errors.append(f"ERROR {VOCABULARY_PATH}: predicates.{name}.broader は述語名の文字列でなければならない")
            elif broader == name:
                errors.append(f"ERROR {VOCABULARY_PATH}: predicates.{name}.broader が自身を指している")
            elif is_unclassified(broader):
                errors.append(
                    f"ERROR {VOCABULARY_PATH}: predicates.{name}.broader に '{broader}' は使えない"
                    "（未分類の印であり、述語の親にならない）"
                )
            elif broader not in predicates:
                errors.append(f"ERROR {VOCABULARY_PATH}: predicates.{name}.broader に未知の述語 '{broader}'")
            else:
                # 循環の有無にかかわらず、直接の親との domain / range の包含は検査する
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
        parent = _parent(predicates, name)
        if parent is not None:
            item["broader"] = parent
        if isinstance(predicate.maps_to, list) and predicate.maps_to:
            item["maps_to"] = [str(entry) for entry in predicate.maps_to]
        if item:
            exported[name] = item
    return exported
