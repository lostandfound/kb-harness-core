"""ビュー: エンティティ本文の外に置く、束ねと導出の定義。

ビューは `kb-domain.yml` の `views.root` 配下に 1 件 1 YAML で置く。エンティティ
Markdown には書き戻さない。事実（出典で支えられた記述）はエンティティに、
解釈（書き手の見方による束ね）はビューに、という分離を機械的に保つための層である。

- `kind: list`  は割り当てビュー。メンバーを列挙する。`basis` で解釈か出典由来かを言う。
- `kind: query` は導出ビュー。`where` の AND 条件でメンバーを計算する。新しい情報を持たない。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Collection, Mapping

import yaml

from .validation import (
    FILENAME_RE,
    _load_references,
    _load_types,
    _load_vocabulary,
    _iter_entity_files,
    _parse_frontmatter,
)


KINDS = ("list", "query")
BASES = ("interpretation", "source")
WHERE_KEYS = ("type", "tags", "relation")
VIEW_KEYS = ("name", "description", "kind", "basis", "members", "where", "sources")


@dataclass(frozen=True)
class ViewMember:
    path: str
    note: str = ""


@dataclass(frozen=True)
class View:
    id: str
    path: Path
    name: str
    description: str
    kind: str
    basis: str | None = None
    members: tuple[ViewMember, ...] = ()
    where: Mapping[str, Any] = field(default_factory=dict)
    sources: tuple[str, ...] = ()


class ViewError(ValueError):
    def __init__(self, message: str, code: str = "view.invalid"):
        super().__init__(message)
        self.code = code


def load_entities(content_root: Path) -> dict[str, dict]:
    entities: dict[str, dict] = {}
    for path in _iter_entity_files(content_root):
        if path.name == "index.md" or path.name == "vocabulary.yml":
            continue
        frontmatter, _body, error = _parse_frontmatter(path)
        if error or frontmatter is None:
            continue
        entities["/" + str(path.relative_to(content_root))] = frontmatter
    return entities


def _view_files(views_root: Path) -> list[Path]:
    if not views_root.is_dir():
        return []
    return sorted(
        path for path in views_root.glob("*.yml") if path.is_file()
    ) + sorted(path for path in views_root.glob("*.yaml") if path.is_file())


def _parse_members(raw: Any) -> tuple[ViewMember, ...] | None:
    if not isinstance(raw, list):
        return None
    members: list[ViewMember] = []
    for item in raw:
        if isinstance(item, str):
            members.append(ViewMember(item))
        elif isinstance(item, dict) and isinstance(item.get("path"), str):
            note = item.get("note", "")
            members.append(ViewMember(item["path"], str(note) if note is not None else ""))
        else:
            return None
    return tuple(members)


def load_view(path: Path) -> View:
    """1 件のビュー YAML を読む。形式の不備は ViewError。"""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise ViewError(f"{path.name}: invalid YAML: {error}", "view.yaml") from error
    if not isinstance(data, dict):
        raise ViewError(f"{path.name}: view must be a mapping", "view.spec")
    unknown = sorted(set(data) - set(VIEW_KEYS))
    if unknown:
        raise ViewError(f"{path.name}: unknown key(s): {', '.join(unknown)}", "view.spec")
    for key in ("name", "description", "kind"):
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ViewError(f"{path.name}: missing required field '{key}'", "view.spec")
    kind = data["kind"]
    if kind not in KINDS:
        raise ViewError(f"{path.name}: kind must be one of {', '.join(KINDS)}", "view.spec")

    basis = data.get("basis")
    members: tuple[ViewMember, ...] = ()
    where: Mapping[str, Any] = {}
    sources = data.get("sources") or []
    if not isinstance(sources, list) or not all(isinstance(s, str) and s.strip() for s in sources):
        raise ViewError(f"{path.name}: sources must be a list of non-empty strings", "view.spec")

    if kind == "list":
        if "where" in data:
            raise ViewError(f"{path.name}: list view must not have 'where'", "view.spec")
        parsed = _parse_members(data.get("members"))
        if not parsed:
            raise ViewError(
                f"{path.name}: list view requires non-empty 'members' (paths or {{path, note}})",
                "view.spec",
            )
        members = parsed
        if basis not in BASES:
            raise ViewError(f"{path.name}: list view requires basis in {', '.join(BASES)}", "view.spec")
        if basis == "source" and not sources:
            raise ViewError(f"{path.name}: basis 'source' requires non-empty 'sources'", "view.spec")
        if basis == "interpretation" and sources:
            raise ViewError(
                f"{path.name}: basis 'interpretation' must not carry 'sources' (use basis 'source')",
                "view.spec",
            )
    else:
        for key in ("members", "basis", "sources"):
            if key in data:
                raise ViewError(f"{path.name}: query view must not have '{key}'", "view.spec")
        raw_where = data.get("where")
        if not isinstance(raw_where, dict) or not raw_where:
            raise ViewError(f"{path.name}: query view requires non-empty 'where'", "view.spec")
        unknown_where = sorted(set(raw_where) - set(WHERE_KEYS))
        if unknown_where:
            raise ViewError(
                f"{path.name}: where has unknown key(s): {', '.join(unknown_where)}", "view.spec"
            )
        if "type" in raw_where and not isinstance(raw_where["type"], str):
            raise ViewError(f"{path.name}: where.type must be a string", "view.spec")
        if "tags" in raw_where and (
            not isinstance(raw_where["tags"], list)
            or not all(isinstance(t, str) for t in raw_where["tags"])
        ):
            raise ViewError(f"{path.name}: where.tags must be a list of strings", "view.spec")
        if "relation" in raw_where:
            relation = raw_where["relation"]
            if (
                not isinstance(relation, dict)
                or not isinstance(relation.get("predicate"), str)
                or not isinstance(relation.get("target"), str)
            ):
                raise ViewError(
                    f"{path.name}: where.relation requires 'predicate' and 'target'", "view.spec"
                )
        where = dict(raw_where)

    return View(
        id=path.stem,
        path=path,
        name=data["name"].strip(),
        description=data["description"].strip(),
        kind=kind,
        basis=basis,
        members=members,
        where=where,
        sources=tuple(sources),
    )


def _duplicate_ids(paths: list[Path]) -> dict[str, list[str]]:
    """同じ stem を .yml と .yaml で置くと id が衝突する。id → ファイル名一覧を返す。"""
    by_id: dict[str, list[str]] = {}
    for path in paths:
        by_id.setdefault(path.stem, []).append(path.name)
    return {view_id: names for view_id, names in by_id.items() if len(names) > 1}


def load_views(views_root: Path) -> list[View]:
    """views_root 配下の全ビューを id 順に返す。形式不備は最初の 1 件で ViewError。"""
    paths = _view_files(views_root)
    duplicates = _duplicate_ids(paths)
    if duplicates:
        view_id, names = sorted(duplicates.items())[0]
        raise ViewError(f"duplicate view id '{view_id}': {', '.join(names)}", "view.duplicate")
    views = [load_view(path) for path in paths]
    views.sort(key=lambda view: view.id)
    return views


def query_excluded_types(content_root: Path) -> frozenset[str]:
    """query の対象から外す型。export_graph がノードにしない型（Claim / Index / graph: false）と揃える。"""
    types = _load_types(content_root)
    return frozenset(
        {"Claim", "Index"}
        | {name for name, definition in types.items() if not definition.get("graph", True)}
    )


def resolve_view(
    view: View,
    entities: Mapping[str, dict],
    excluded: Collection[str] = ("Claim", "Index"),
) -> list[ViewMember]:
    """ビューのメンバーを確定する。query は entities を AND 条件で絞る。

    excluded は語彙を読まずに済む既定値。graph: false の型も外すには
    query_excluded_types(content_root) を渡す。
    """
    if view.kind == "list":
        return list(view.members)
    wanted_type = view.where.get("type")
    wanted_tags = set(view.where.get("tags") or [])
    relation = view.where.get("relation")
    hits: list[ViewMember] = []
    for path in sorted(entities):
        frontmatter = entities[path]
        # graph.json の nodes に出ないものを拾うと、views[].members が nodes に無いパスを指す
        if frontmatter.get("type") in excluded:
            continue
        if wanted_type is not None and frontmatter.get("type") != wanted_type:
            continue
        if wanted_tags and not wanted_tags.issubset(set(frontmatter.get("tags") or [])):
            continue
        if relation is not None:
            matched = any(
                isinstance(entry, dict)
                and entry.get("predicate") == relation["predicate"]
                and entry.get("target") == relation["target"]
                for entry in frontmatter.get("relations") or []
            )
            if not matched:
                continue
        hits.append(ViewMember(path))
    return hits


def validate_views(content_root: Path, views_root: Path) -> list[str]:
    """ビュー定義を KB の語彙と実在エンティティに照らして検査する。

    戻り値は `kb validate` の errors と同じ `ERROR <相対パス>: <内容>` 形式。
    """
    errors: list[str] = []
    if not views_root.is_dir():
        return errors
    entities = load_entities(content_root)
    predicates, vocab_tags = _load_vocabulary(content_root)
    types = _load_types(content_root)
    references, _ref_errors = _load_references(content_root)
    seen_names: dict[str, str] = {}
    paths = _view_files(views_root)
    for view_id, names in sorted(_duplicate_ids(paths).items()):
        errors.append(f"ERROR {views_root.name}/{names[0]}: view id '{view_id}' が重複している（{', '.join(names)}）")
    for path in paths:
        rel = f"{views_root.name}/{path.name}"
        if not FILENAME_RE.match(path.stem + ".md"):
            errors.append(f"ERROR {rel}: ファイル名がケバブケース規約に反する '{path.name}'")
        try:
            view = load_view(path)
        except ViewError as error:
            errors.append(f"ERROR {rel}: {error}")
            continue
        if view.name in seen_names:
            errors.append(f"ERROR {rel}: name '{view.name}' が {seen_names[view.name]} と重複している")
        seen_names.setdefault(view.name, rel)
        for member in view.members:
            if member.path not in entities:
                errors.append(f"ERROR {rel}: member '{member.path}' does not exist")
            elif entities[member.path].get("type") == "Claim":
                errors.append(f"ERROR {rel}: member '{member.path}' は Claim であり、ビューのメンバーにできない")
        for source in view.sources:
            if source.startswith("ref:"):
                ref_id = source[len("ref:"):].strip()
                if ref_id not in references:
                    errors.append(f"ERROR {rel}: sources の 'ref: {ref_id}' が references.yml に存在しない")
        if view.kind == "query":
            wanted_type = view.where.get("type")
            if wanted_type is not None and wanted_type not in types:
                errors.append(f"ERROR {rel}: where.type に未知の型 '{wanted_type}'")
            for tag in view.where.get("tags") or []:
                if tag not in vocab_tags:
                    errors.append(f"ERROR {rel}: where.tags に未知のタグ '{tag}'")
            relation = view.where.get("relation")
            if relation is not None:
                if relation["predicate"] not in predicates:
                    errors.append(f"ERROR {rel}: where.relation に未知の述語 '{relation['predicate']}'")
                if relation["target"] not in entities:
                    errors.append(f"ERROR {rel}: where.relation の target '{relation['target']}' does not exist")
    return errors


def export_views(content_root: Path, views_root: Path) -> list[dict[str, Any]]:
    """graph.json の `views` 要素。メンバーは解決済みのパス一覧。"""
    entities = load_entities(content_root)
    exported: list[dict[str, Any]] = []
    excluded = query_excluded_types(content_root)
    for view in load_views(views_root):
        item: dict[str, Any] = {
            "id": view.id,
            "name": view.name,
            "description": view.description,
            "kind": view.kind,
        }
        if view.basis is not None:
            item["basis"] = view.basis
        if view.kind == "query":
            item["where"] = dict(view.where)
        item["members"] = [member.path for member in resolve_view(view, entities, excluded)]
        exported.append(item)
    return exported


INDEX_HEADING = "# ビュー一覧"
INDEX_NOTE = (
    "エンティティ本文の外で定義した束ねと導出の一覧。`kb sync` が生成するので手で編集しない。"
    "`basis: interpretation` は書き手の見方であり、出典に基づく事実ではない。"
)


def render_views_index(content_root: Path, views_root: Path) -> str:
    entities = load_entities(content_root)
    excluded = query_excluded_types(content_root)
    lines = [INDEX_HEADING, "", INDEX_NOTE, ""]
    for view in load_views(views_root):
        members = resolve_view(view, entities, excluded)
        lines.append(f"## {view.name}")
        lines.append("")
        lines.append(view.description)
        lines.append("")
        meta = [f"kind: {view.kind}"]
        if view.basis is not None:
            meta.append(f"basis: {view.basis}")
        meta.append(f"定義: {views_root.name}/{view.path.name}")
        lines.append(" / ".join(meta))
        lines.append("")
        if view.sources:
            lines.append("出典: " + "、".join(view.sources))
            lines.append("")
        for member in members:
            frontmatter = entities.get(member.path) or {}
            title = str(frontmatter.get("title") or member.path)
            note = f" — {member.note}" if member.note else ""
            lines.append(f"- [{title}]({member.path}){note}")
        if not members:
            lines.append("- （該当なし）")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def plan_views_index(content_root: Path, views_root: Path | None, index_path: Path | None) -> dict[Path, str]:
    """ビュー一覧の生成計画。views が未設定なら空。"""
    if views_root is None or index_path is None or not views_root.is_dir():
        return {}
    rendered = render_views_index(content_root, views_root)
    output = index_path.resolve()
    current = output.read_text(encoding="utf-8") if output.is_file() else None
    if current == rendered:
        return {}
    return {output: rendered}

