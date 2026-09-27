#!/usr/bin/env python3
import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .diagnostics import Diagnostic, HarnessError
from .links import body_links, is_root_relative, resolve_link
from .markdown import field_text, frontmatter_scalar_text, parse_document
from .naming import validate_vocabulary_names_at
from .ontology import build_ontology, validate_claim
from .predicates import (
    Predicate,
    as_mapping,
    is_unclassified,
    predicates_from_mapping,
    refinement_candidates,
    validate_predicates,
)
from .project import Project, ProjectError
from .types import load_types, validate_type_fields


def default_content_root() -> str:
    """Resolve the configured root while preserving the legacy CLI default."""
    last_error: ProjectError | None = None
    for start in (Path.cwd(), Path(__file__).resolve().parents[2]):
        try:
            project = Project.discover(start)
        except ProjectError as error:
            last_error = error
            continue
        return str(project.content_root)
    raise FileNotFoundError(str(last_error)) from last_error

REQUIRED_FIELDS = ["type", "title", "description", "tags", "timestamp"]
TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
PERSON_DATE_RE = re.compile(r"^(\d{4}\??|\d{4}頃|不詳)$")
FILENAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*\.md$")
LIST_FIELDS = ("tags", "sources", "relations", "aliases")
TITLE_PAREN_RE = re.compile(r"[（(]")
# description は RAG の検索で最初に当たる値であり、index.md にも転記される。
# 改版で前の版の断片が残っても形式は壊れないため、内容の側を検査する。
DESCRIPTION_SENTENCE_RE = re.compile(r"[^。．.!?！？]+[。．.!?！？]?")
DESCRIPTION_LONG = 240
DESCRIPTION_MIN_SHARED = 8
# 本文インライン出典表記（（出典: ref-id, ref-id））。全角括弧のみ対応。
CITATION_MARKER_RE = re.compile(r"（出典")
CITATION_RE = re.compile(r"（出典:\s*([^（）]*)）")
# LLM 生成時に混入しうるラッパータグ（本文は純 Markdown であり HTML タグを含まない前提）
ARTIFACT_RE = re.compile(r"</?(content|document|file|output|text)>", re.IGNORECASE)

class ValidationWarning(str):
    """validate() の warning。従来どおり文字列として印字でき、severity / code を併せ持つ。

    文字列形は `<SEVERITY> <message>`。scripts/validate.py はそのまま stderr に出し、
    `kb validate --format json` は warning_record で構造化する。
    """

    severity: str
    code: str

    def __new__(cls, message: str, *, code: str, severity: str = "warning"):
        instance = super().__new__(cls, f"{severity.upper()} {message}")
        instance.severity = severity
        instance.code = code
        return instance


def warning_record(warning: str) -> dict[str, str]:
    """warning を `diagnostics` と同じ構造（severity / code / message）にする。"""
    if isinstance(warning, ValidationWarning):
        return {"severity": warning.severity, "code": warning.code, "message": str(warning)}
    return {"severity": "warning", "code": "validation.warning", "message": str(warning)}


def _read_vocabulary(root: Path) -> tuple[dict, set[str], dict[str, Predicate]]:
    """vocabulary.yml を 1 回読み、述語（Ontology 用の写像と Predicate）とタグを返す。"""
    data = yaml.safe_load((root / "vocabulary.yml").read_text(encoding="utf-8")) or {}
    predicate_defs = predicates_from_mapping(data.get("predicates"))
    tags = set(data.get("tags") or [])
    return as_mapping(predicate_defs), tags, predicate_defs


def _load_vocabulary(root: Path):
    predicates, tags, _defs = _read_vocabulary(root)
    return predicates, tags

def _load_properties(root: Path) -> dict:
    data = yaml.safe_load((root / "vocabulary.yml").read_text(encoding="utf-8")) or {}
    properties = {}
    for name, val in (data.get("properties") or {}).items():
        if isinstance(val, dict):
            properties[name] = {
                "description": val.get("description", ""),
                "domain": val.get("domain") or [],
                "value_type": val.get("value_type", "string"),
            }
        else:
            properties[name] = {"description": val, "domain": [], "value_type": "string"}
    return properties


def _load_types(root: Path) -> dict:
    """vocabulary.yml の types: セクションを読み込む（kb_harness.types.load_types の必須版）。

    types: が定義されていなければ、entity type の体系そのものが
    未定義でありフォールバックの余地が無いため例外を送出する。
    """
    types = load_types(root)
    if not types:
        raise ValueError(f"vocabulary.yml に 'types' セクションが定義されていない: {root / 'vocabulary.yml'}")
    return types


def _load_references(root: Path):
    """references.yml を読み込み、(refs, errors) を返す。ファイルが無ければ空扱い。

    読み込み・per-entry の検査規則は `kb_harness.references` の
    `load_registry` / `check_reference_entry` に一本化されている
    （`kb reference health` / `kb reference create` と共通）。
    `references` はここから `sync` → `views` → `validation` と循環
    import になるため、モジュール読み込み時ではなく呼び出し時に import する。
    """
    from .references import ReferenceSpecError, check_reference_entry, load_registry

    ref_path = root / "references.yml"
    try:
        data, duplicate_ids = load_registry(ref_path)
    except ReferenceSpecError as error:
        return {}, [f"ERROR /references.yml: {error}"]
    errors: list[str] = [
        f"ERROR /references.yml: '{ref_id}' duplicate reference id" for ref_id in duplicate_ids
    ]
    for ref_id in sorted(data, key=str):
        for diagnostic in check_reference_entry(ref_id, data[ref_id]):
            errors.append(f"ERROR /references.yml: {diagnostic['message']}")
    return data, errors


def _validate_evals(root: Path, all_paths: set[str], repo_root: Path | None = None) -> list[str]:
    """evals/rag-eval.yml（リポジトリルート直下、content_root の外）を検証する。ファイルが無ければ空扱い。

    `repo_root` を渡さない呼び出しは、旧来どおり `content_root` の親をリポジトリルートとみなす。
    `content_root: kb/entities` のように content_root がリポジトリルート直下にない配置では
    これが誤りで、`evals/` を静かに見失う（staging.py / cli.py は常に `project.repo_root` を渡す）。
    """
    base = repo_root if repo_root is not None else root.parent
    evals_path = base / "evals" / "rag-eval.yml"
    if not evals_path.exists():
        return []
    rel = "/evals/rag-eval.yml"
    data = yaml.safe_load(evals_path.read_text(encoding="utf-8")) or []
    errors: list[str] = []
    if isinstance(data, dict):
        data = data.get("entries")
    if not isinstance(data, list):
        return [f"ERROR {rel}: must be a list"]

    seen_ids: set[str] = set()
    for entry in data:
        if not isinstance(entry, dict):
            errors.append(f"ERROR {rel}: entry must be a mapping")
            continue
        entry_id = entry.get("id")
        if not entry_id:
            errors.append(f"ERROR {rel}: entry missing required field 'id'")
            continue
        if entry_id in seen_ids:
            errors.append(f"ERROR {rel}: '{entry_id}' の id が重複している")
        else:
            seen_ids.add(entry_id)

        for field in ("query", "expected", "evidence"):
            if not entry.get(field):
                errors.append(f"ERROR {rel}: '{entry_id}' missing required field '{field}'")

        evidence = entry.get("evidence")
        if evidence:
            if not isinstance(evidence, list):
                errors.append(f"ERROR {rel}: '{entry_id}' の 'evidence' はリスト型である必要がある")
            else:
                for ev in evidence:
                    if ev not in all_paths:
                        errors.append(f"ERROR {rel}: '{entry_id}' の evidence '{ev}' がバンドルに存在しない")

    return errors


def _iter_entity_files(root: Path):
    for path in sorted(root.rglob("*.md")):
        yield path


def _parse_frontmatter(path: Path):
    text = path.read_text(encoding="utf-8")
    try:
        document = parse_document(str(path), text)
    except HarnessError as error:
        return None, None, error.diagnostic.message
    return document.frontmatter, document.body, None


def _contains_todo(value) -> bool:
    if isinstance(value, str):
        return "TODO" in value
    if isinstance(value, dict):
        return any(_contains_todo(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_todo(v) for v in value)
    return False



def _check_description(rel: str, description: str) -> list[str]:
    """description の内容が壊れていないかを検査する。

    必須フィールドの有無だけでは、改版で前の版の断片が残った description を
    検出できない。形式は正しいまま、検索結果と index に重複した文が出続ける。
    """
    errors: list[str] = []
    text = description.strip()
    if not text:
        errors.append(f"ERROR {rel}: description が空である")
        return errors

    # 消し残りは前の版の完全な文とは限らず、途中で切れた断片が残る。完全一致では
    # なく末尾の重なりを見ることでその形も拾う。短い語尾の一致は文体上ありうるので、
    # 一定の長さを超える重なりだけを重複と見なす。
    cores = [
        core
        for core in (
            match.group().strip(" 　").rstrip("。．.!?！？").strip()
            for match in DESCRIPTION_SENTENCE_RE.finditer(text)
        )
        if len(core) >= DESCRIPTION_MIN_SHARED
    ]
    for i, first in enumerate(cores):
        for second in cores[i + 1:]:
            shared = _common_suffix(first, second)
            if len(shared) >= DESCRIPTION_MIN_SHARED:
                errors.append(f"ERROR {rel}: description に同じ記述が繰り返されている '{shared}'")
                return errors

    return errors


def _common_suffix(a: str, b: str) -> str:
    """末尾から一致する部分を返す。"""
    n = 0
    while n < min(len(a), len(b)) and a[-1 - n] == b[-1 - n]:
        n += 1
    return a[len(a) - n:] if n else ""

def validate(root: Path, warnings: list[str] | None = None, repo_root: Path | None = None) -> list[str]:
    errors: list[str] = []
    if warnings is None:
        warnings = []
    predicates, vocab_tags, predicate_defs = _read_vocabulary(root)
    properties = _load_properties(root)
    # 述語の階層（broader / maps_to）は kb-ontology-core には渡さず、ハーネス側で検査する
    errors.extend(validate_predicates(predicate_defs))
    types = _load_types(root)
    errors.extend(f"ERROR vocabulary.yml: {problem}" for problem in validate_type_fields(types))
    errors.extend(f"ERROR vocabulary.yml: {problem}" for problem in validate_vocabulary_names_at(root))
    # directory を欠く型（vocabulary.yml.directory が未設定）は validate_type_fields が
    # 別途 ERROR にする。ここで拾うと None がディレクトリ名として type_dir_map に入り、
    # ルート index が存在しない '/None/index.md' を要求してしまう。
    type_dir_map = {
        t["directory"]: name
        for name, t in types.items()
        if isinstance(t.get("directory"), str) and t["directory"].strip()
    }
    references, ref_errors = _load_references(root)
    errors.extend(ref_errors)
    used_references: set[str] = set()

    entities = {}
    for path in _iter_entity_files(root):
        if path.name == "vocabulary.yml":
            continue
        rel = "/" + str(path.relative_to(root))
        fm, body, err = _parse_frontmatter(path)
        if err:
            errors.append(f"ERROR {rel}: {err}")
            continue
        entities[rel] = (path, fm, body)

    all_paths = set(entities.keys())
    expected_index_links = {f"/{d}/index.md" for d in type_dir_map}
    edges: list[tuple[str, str, str, str]] = []
    claims: list[tuple[str, dict]] = []
    root_relative_links: dict[str, int] = {}

    unknown_dirs = {
        rel.split("/")[1] for rel in all_paths
        if "/" in rel.lstrip("/") and rel.lstrip("/").split("/")[0] not in type_dir_map
    }
    for dirname in sorted(unknown_dirs):
        errors.append(f"ERROR /{dirname}: 未知のトップレベルディレクトリに .md ファイルが存在する")

    # content_root 直下は index.md 専用である。型ディレクトリを介さない .md
    # （例: /stray.md）は「/」を含まないので unknown_dirs の対象にならず、
    # type_dir_map.get(dirname) も None のまま黙って通ってしまう（後段の型検査を素通りし graph.json に載る）。
    stray_root_files = {
        rel for rel in all_paths
        if "/" not in rel.lstrip("/") and rel != "/index.md"
    }
    for rel in sorted(stray_root_files):
        errors.append(f"ERROR {rel}: content_root 直下には index.md 以外の .md ファイルを置けない（型ディレクトリの下に置く）")

    errors.extend(_validate_evals(root, all_paths, repo_root))

    for rel, (path, fm, body) in entities.items():
        dirname = path.relative_to(root).parts[0]
        is_index = path.name == "index.md"

        for field in REQUIRED_FIELDS:
            if field not in fm or fm[field] in (None, ""):
                errors.append(f"ERROR {rel}: missing required field '{field}'")

        if _contains_todo(fm):
            errors.append(f"ERROR {rel}: frontmatter に TODO プレースホルダ")

        if body and "TODO" in body:
            errors.append(f"ERROR {rel}: 本文に TODO プレースホルダ")

        if body and ARTIFACT_RE.search(body):
            errors.append(f"ERROR {rel}: 本文に生成アーティファクト（ラッパータグ）が混入")

        if body:
            citation_matches = list(CITATION_RE.finditer(body))
            if len(CITATION_MARKER_RE.findall(body)) != len(citation_matches):
                errors.append(f"ERROR {rel}: 本文の出典表記の書式が不正（（出典: ref-id）の形式で閉じ括弧が必要）")
            for cm in citation_matches:
                ref_ids = [r.strip() for r in cm.group(1).split(",") if r.strip()]
                if not ref_ids:
                    errors.append(f"ERROR {rel}: 本文の出典表記に ref-id が指定されていない")
                for ref_id in ref_ids:
                    if ref_id not in references:
                        errors.append(f"ERROR {rel}: 本文の出典表記 'ref: {ref_id}' が references.yml に存在しない")
                    else:
                        used_references.add(ref_id)

        if not FILENAME_RE.match(path.name):
            errors.append(f"ERROR {rel}: ファイル名がケバブケース規約に反する '{path.name}'")

        # YAML が datetime に変換すると元の表記が失われるため、スカラーの元値も検査する。
        timestamp = fm.get("timestamp")
        if timestamp is not None:
            if isinstance(timestamp, str):
                if not TIMESTAMP_RE.fullmatch(timestamp):
                    errors.append(f"ERROR {rel}: timestamp の形式が不正 '{timestamp}'")
            elif isinstance(timestamp, datetime):
                original = frontmatter_scalar_text(path.read_text(encoding="utf-8"), "timestamp")
                if original is None or not TIMESTAMP_RE.fullmatch(original):
                    errors.append(f"ERROR {rel}: timestamp は UTC 秒精度の 'YYYY-MM-DDTHH:MM:SSZ' である必要がある '{timestamp}'")
            else:
                errors.append(f"ERROR {rel}: timestamp は文字列である必要がある")

        for field in ("title", "description"):
            value = fm.get(field)
            if value is not None and not isinstance(value, str):
                errors.append(f"ERROR {rel}: '{field}' は文字列である必要がある（YAML が {type(value).__name__} に解決）")

        for field in LIST_FIELDS:
            value = fm.get(field)
            if value is not None and not isinstance(value, list):
                errors.append(f"ERROR {rel}: '{field}' はリスト型である必要がある")

        title = fm.get("title")
        if isinstance(title, str) and TITLE_PAREN_RE.search(title):
            errors.append(f"ERROR {rel}: title に括弧を含めてはならない '{title}'")

        description = fm.get("description")
        if isinstance(description, str):
            errors.extend(_check_description(rel, description))
            if isinstance(title, str) and description.strip() == title.strip():
                warnings.append(
                    ValidationWarning(
                        f"{rel}: description が title と同一で説明になっていない",
                        code="validation.description.same_as_title",
                    )
                )
            if len(description.strip()) > DESCRIPTION_LONG:
                warnings.append(
                    ValidationWarning(
                        f"{rel}: description が長い（{len(description.strip())} 文字）。検索結果に出る一文として読めるか見直す",
                        code="validation.description.long",
                    )
                )

        aliases = fm.get("aliases")
        if isinstance(aliases, list):
            for alias in aliases:
                if not isinstance(alias, str) or not alias.strip():
                    errors.append(f"ERROR {rel}: aliases に空文字を含めてはならない")
                elif alias == title:
                    errors.append(f"ERROR {rel}: aliases '{alias}' が自身の title と重複している")

        entity_type = fm.get("type")
        type_def = types.get(entity_type)
        sources_required = (type_def or {}).get("sources_required", True)
        if not is_index:
            sources = fm.get("sources")
            if not sources:
                if sources_required:
                    errors.append(f"ERROR {rel}: missing required field 'sources'")
            elif isinstance(sources, list):
                for source in sources:
                    if not isinstance(source, str) or not source.startswith("ref:"):
                        continue
                    ref_id = source[len("ref:"):].strip()
                    if ref_id not in references:
                        errors.append(f"ERROR {rel}: sources の 'ref: {ref_id}' が references.yml に存在しない")
                    else:
                        used_references.add(ref_id)

        declared_fields = [(field, True) for field in (type_def or {}).get("extra_fields") or []]
        declared_fields += [(field, False) for field in (type_def or {}).get("optional_fields") or []]
        for field, required in declared_fields:
            # キーが無いか、`died:` のように値が空（YAML の None）なら書いていないものとして扱う
            if fm.get(field) is None:
                if required:
                    errors.append(f"ERROR {rel}: missing required field '{field}'")
                continue
            value = field_text(fm.get(field))
            if value is None:
                errors.append(f"ERROR {rel}: '{field}' は非空の文字列でなければならない（値: {fm.get(field)!r}）")
            elif field in ("born", "died") and not PERSON_DATE_RE.match(value):
                errors.append(f"ERROR {rel}: '{field}' の形式が不正 '{value}'")

        if is_index:
            if entity_type != "Index":
                errors.append(f"ERROR {rel}: type must be 'Index' for index.md")
        else:
            expected_type = type_dir_map.get(dirname)
            if expected_type and entity_type != expected_type:
                errors.append(
                    f"ERROR {rel}: type '{entity_type}' does not match directory "
                    f"'{dirname}' (expected '{expected_type}')"
                )

        for tag in fm.get("tags") or []:
            if tag not in vocab_tags:
                errors.append(f"ERROR {rel}: unknown tag '{tag}'")

        if type_def is not None and not type_def["graph"] and fm.get("relations"):
            errors.append(f"ERROR {rel}: {entity_type} は relations を持てない")

        for rel_entry in fm.get("relations") or []:
            if not isinstance(rel_entry, dict) or "predicate" not in rel_entry or "target" not in rel_entry:
                errors.append(f"ERROR {rel}: relation missing 'predicate' or 'target'")
                continue
            predicate = rel_entry["predicate"]
            target = rel_entry["target"]
            confidence = rel_entry.get("confidence")
            if confidence is not None and confidence != "C":
                errors.append(f"ERROR {rel}: relations の 'confidence' は 'C' のみ許容（他は省略）'{confidence}'")
            predicate_def = predicates.get(predicate)
            if predicate_def is None:
                errors.append(f"ERROR {rel}: unknown predicate '{predicate}'")
            if target not in all_paths:
                errors.append(f"ERROR {rel}: relation target '{target}' does not exist")
            elif predicate_def is not None:
                domain = predicate_def["domain"]
                range_ = predicate_def["range"]
                target_type = entities[target][1].get("type")
                domain_violation = domain and entity_type not in domain
                range_violation = range_ and target_type not in range_
                if domain_violation or range_violation:
                    errors.append(
                        f"ERROR {rel}: relations predicate {predicate} の型制約違反"
                        f"（{entity_type}→{target_type}）"
                    )
                edges.append((rel, predicate, target))

        if entity_type == "Claim":
            claims.append((rel, fm))

        linked: set[str] = set()
        for link in body_links(body or ""):
            if is_root_relative(link):
                root_relative_links[rel] = root_relative_links.get(rel, 0) + 1
            target = resolve_link(rel, link)
            if target is None:
                # content_root の外（リポジトリ内の文書など）はファイルの実在だけを見る
                if not (path.parent / link).exists():
                    errors.append(f"ERROR {rel}: broken link '{link}'")
                continue
            linked.add(target)
            if target not in all_paths:
                errors.append(f"ERROR {rel}: broken link '{link}'")

        if is_index and path.parent != root:
            siblings = {
                "/" + str(p.relative_to(root))
                for p in (path.parent).glob("*.md")
                if p.name != "index.md"
            }
            for missing in siblings - linked:
                errors.append(f"ERROR {rel}: index missing entity link '{missing}'")
            for extra in linked - siblings:
                errors.append(f"ERROR {rel}: index links non-existent entity '{extra}'")

        if is_index and path.parent == root:
            for missing in expected_index_links - linked:
                errors.append(f"ERROR {rel}: ルート index に必須カテゴリリンク欠落 '{missing}'")

    if root_relative_links:
        # 旧形式は GitHub で遷移できないだけで解決はできるので、ERROR にせず件数で促す
        warnings.append(
            ValidationWarning(
                f"ルート相対の本文リンク {sum(root_relative_links.values())} 件"
                f"（{len(root_relative_links)} ファイル）。`kb link migrate` で相対リンクに書き換えられる",
                code="validation.link.root_relative",
            )
        )

    all_titles = {fm.get("title"): rel for rel, (_p, fm, _b) in entities.items() if fm.get("title")}
    alias_owners: dict[str, list[str]] = {}
    for rel, (_path, fm, _body) in entities.items():
        for alias in fm.get("aliases") or []:
            if not isinstance(alias, str) or not alias.strip() or alias == fm.get("title"):
                continue
            title_owner = all_titles.get(alias)
            if title_owner and title_owner != rel:
                errors.append(
                    f"ERROR {rel}: aliases '{alias}' が他エンティティ {title_owner} の title と衝突している"
                )
            alias_owners.setdefault(alias, []).append(rel)
    for alias, owners in alias_owners.items():
        if len(owners) > 1:
            for rel in owners:
                errors.append(f"ERROR {rel}: aliases '{alias}' が複数エンティティ間で重複している")

    edge_keys = {(source, predicate, target) for source, predicate, target in edges}
    entity_types = {path: data[1].get("type") for path, data in entities.items()}
    if claims:
        # kb-ontology-core はここで初めて要る。Claim の無い KB はオントロジーコアなしで検証できる
        ontology = build_ontology({"predicates": predicates, "properties": properties})
        for claim_rel, claim in claims:
            errors.extend(validate_claim(claim_rel, claim, entity_types, ontology, edge_keys))

    seen: dict[tuple[str, str, str], str] = {}
    for source_rel, predicate, target in edges:
        key = (source_rel, predicate, target)
        if key in seen:
            errors.append(
                f"ERROR {source_rel}: relations 重複エッジ ({source_rel}, {predicate}, {target})"
            )
        else:
            seen[key] = source_rel
        if source_rel != target:
            reverse_key = (target, predicate, source_rel)
            if reverse_key in seen:
                errors.append(
                    f"ERROR {source_rel}: relations 逆向きエッジ ({predicate}) が "
                    f"{target} との間に双方向で存在"
                )

    # related-to は未分類の印。件数は分類の負債量として報告し、層 1 のちょうど 1 つの述語に
    # 収まるエッジは精緻化の余地として指す
    unclassified_edges = [
        (source_rel, target) for source_rel, predicate, target in edges if is_unclassified(predicate)
    ]
    for source_rel, target in unclassified_edges:
        candidates = refinement_candidates(
            predicate_defs, entity_types.get(source_rel), entity_types.get(target)
        )
        if len(candidates) == 1:
            warnings.append(
                ValidationWarning(
                    f"{source_rel}: related-to → {target} は '{candidates[0]}' に精緻化できる可能性がある"
                    f"（{entity_types.get(source_rel)}→{entity_types.get(target)}）",
                    code="validation.relation.refinable",
                )
            )
    if unclassified_edges:
        warnings.append(
            ValidationWarning(
                f"relations: related-to のエッジ {len(unclassified_edges)} 件（未分類）",
                code="validation.relation.unclassified",
                severity="info",
            )
        )

    pending_unreferenced_count = 0
    for ref_id, entry in references.items():
        pending = entry.get("pending") if isinstance(entry, dict) else None
        if ref_id not in used_references:
            if pending:
                # pending は「実見待ち等で先行登録した」意図的な未参照なので、個別 WARNING ではなく件数集計にまとめる
                pending_unreferenced_count += 1
            else:
                warnings.append(
                    ValidationWarning(
                        f"/references.yml: '{ref_id}' はどのエンティティからも参照されていない",
                        code="validation.reference.unreferenced",
                    )
                )
        elif pending:
            warnings.append(
                ValidationWarning(
                    f"/references.yml: '{ref_id}' は pending だが参照されている（解除忘れの可能性）",
                    code="validation.reference.pending_referenced",
                )
            )
    if pending_unreferenced_count:
        warnings.append(
            ValidationWarning(
                f"references.yml: pending の未参照エントリ {pending_unreferenced_count} 件（意図的未参照）",
                code="validation.reference.pending_unreferenced",
                severity="info",
            )
        )

    return errors


# urllib デフォルト UA は Wikipedia 等にボット扱いで 403 拒否されるため明示する
_UA = {"User-Agent": "kb-harness-validator/1.0 (+https://github.com/lostandfound/kb-harness-core)"}


def _url_reachable(url: str) -> bool:
    # 日本語等の非 ASCII パスは urllib が扱えないため IRI → URI 変換する
    url = urllib.parse.quote(url, safe=":/?#[]@!$&'()*+,;=%")
    req = urllib.request.Request(url, method="HEAD", headers=_UA)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status < 400
    except urllib.error.HTTPError as e:
        # HEAD 拒否サーバ（405、ボット対策の 403）には GET でフォールバック
        if e.code in (403, 405):
            get_req = urllib.request.Request(url, method="GET", headers=_UA)
            try:
                with urllib.request.urlopen(get_req, timeout=10) as resp:
                    return resp.status < 400
            except Exception:
                return False
        return False
    except Exception:
        return False


def run_extra_checks(commands, cwd: Path) -> list[dict]:
    """kb-domain.yml の validate.extra_checks を順に実行し、結果を構造化して返す。

    シェル経由で実行するのは、導入先がリダイレクトや引数付きの一行コマンドを
    そのまま書けるようにするため。失敗しても後続のチェックは続行し、まとめて報告する。
    """
    import subprocess

    results: list[dict] = []
    for command in commands:
        completed = subprocess.run(
            command, shell=True, cwd=cwd, capture_output=True, text=True
        )
        # 失敗理由が診断メッセージだけで分かるよう stderr の末尾を残す（長大な出力は切る）
        stderr_tail = "\n".join(completed.stderr.strip().splitlines()[-5:])
        results.append(
            {
                "command": command,
                "returncode": completed.returncode,
                "ok": completed.returncode == 0,
                "stderr": stderr_tail,
            }
        )
    return results


def _doi_from_url(url: str) -> str | None:
    parsed = urllib.parse.urlsplit(url)
    if parsed.netloc.lower() not in {"doi.org", "www.doi.org", "dx.doi.org"}:
        return None
    return urllib.parse.unquote(parsed.path.lstrip("/")) or None


def _doi_registered(doi: str) -> bool | None:
    """Check a DOI in the Handle registry without following it to a publisher.

    Returns True when the registry resolves the handle, False when the registry
    answers that it is not registered, and None when the registry could not be
    consulted (network failure, timeout, 5xx, unreadable response).
    """
    handle_url = f"https://doi.org/api/handles/{urllib.parse.quote(doi, safe='/')}"
    req = urllib.request.Request(handle_url, headers={**_UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            record = json.load(resp)
    except urllib.error.HTTPError as e:
        # Handle API は未登録のハンドルに 404（responseCode 100）を返す。それ以外の
        # HTTP エラー（429・5xx 等）はレジストリ側の都合で、登録の有無は分からない
        if e.code == 404:
            return False
        return None
    except Exception:
        return None
    if not isinstance(record, dict):
        return None
    return (
        record.get("responseCode") == 1
        and record.get("handle", "").casefold() == doi.casefold()
    )


def check_urls(root: Path, warnings: list[str] | None = None) -> list[str]:
    """出典 URL と DOI の到達性を確かめ、ERROR の一覧を返す。

    DOI（`references.yml` の `doi` と doi.org の URL）は出版社へ辿らず、DOI レジストリで
    登録の有無だけを見る。レジストリに届かなかった DOI は登録の有無が分からないため
    ERROR にせず、``warnings`` を渡されていればそこへ WARNING として加える。
    """
    errors: list[str] = []

    def check_doi(doi: str, where: str, suffix: str = "") -> None:
        registered = _doi_registered(doi)
        if registered is False:
            errors.append(f"ERROR {where}: DOI unregistered {doi}{suffix}")
        elif registered is None and warnings is not None:
            warnings.append(
                ValidationWarning(
                    f"{where}: DOI レジストリに届かず登録を確認できない {doi}{suffix}",
                    code="validation.url.doi_registry_unreachable",
                )
            )

    for path in _iter_entity_files(root):
        if path.name == "vocabulary.yml":
            continue
        rel = "/" + str(path.relative_to(root))
        fm, _body, err = _parse_frontmatter(path)
        if err or fm is None:
            continue
        for source in fm.get("sources") or []:
            if not isinstance(source, str) or not source.startswith(("http://", "https://")):
                continue
            doi = _doi_from_url(source)
            if doi:
                check_doi(doi, rel)
            elif not _url_reachable(source):
                errors.append(f"ERROR {rel}: unreachable URL {source}")

    references, _ref_errors = _load_references(root)
    for ref_id, entry in references.items():
        if not isinstance(entry, dict):
            continue
        url = entry.get("url")
        doi = entry.get("doi")
        suffix = f" ({ref_id})"
        if doi:
            check_doi(doi, "/references.yml", suffix)
        elif url:
            doi = _doi_from_url(url)
            if doi:
                check_doi(doi, "/references.yml", suffix)
            elif not _url_reachable(url):
                errors.append(f"ERROR /references.yml: unreachable URL {url} ({ref_id})")
    return errors


def fix_timestamps(root: Path) -> list[Path]:
    root = root.resolve()
    toplevel_result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, cwd=str(root),
    )
    if toplevel_result.returncode != 0:
        raise HarnessError(
            Diagnostic(
                code="validation.timestamps.git_required",
                message=(
                    "fix_timestamps requires a git working tree "
                    f"(git rev-parse --show-toplevel failed: {toplevel_result.stderr.strip()})"
                ),
                path=str(root),
            )
        )
    repo_root = Path(toplevel_result.stdout.strip()).resolve()

    # -z: NUL-delimited, rename-safe (no ambiguous " -> " to parse).
    # --untracked-files=all: expand untracked directories so nested .md files aren't collapsed
    # into a single "?? dir/" entry.
    result = subprocess.run(
        ["git", "status", "--porcelain", "-z", "--untracked-files=all", "."],
        capture_output=True, text=True, cwd=str(root),
    )
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    fixed = []

    entries = result.stdout.split("\0")
    i = 0
    while i < len(entries):
        entry = entries[i]
        i += 1
        if not entry:
            continue
        status, filepath = entry[:2], entry[3:]
        if "R" in status or "C" in status:
            # Rename/copy records emit the new path in this field and the old path as the
            # next NUL-delimited field; skip the old path since it no longer exists on disk.
            i += 1
        if not filepath.endswith(".md"):
            continue
        # git status paths are relative to the repository root, not our cwd.
        path = (repo_root / filepath).resolve()
        if root != repo_root and root not in path.parents and path != root:
            continue
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        new_text, n = re.subn(r"(?m)^timestamp:.*$", f"timestamp: {now}", text, count=1)
        if n:
            path.write_text(new_text, encoding="utf-8")
            fixed.append(path)
    return fixed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=None, help="コンテンツルート（省略時は kb-domain.yml から解決）")
    parser.add_argument("--fix-timestamps", action="store_true")
    parser.add_argument("--check-urls", action="store_true")
    args = parser.parse_args()

    # 既定値は parser 構築時ではなく、ここで遅延評価する（--help や --root 指定時に KB 探索で落ちない）
    root = Path(args.root) if args.root else Path(default_content_root())
    if args.fix_timestamps:
        fixed = fix_timestamps(root)
        for path in fixed:
            print(f"fixed timestamp: {path}")

    # evals/ はリポジトリルート直下にあり、kb-domain.yml から辿れればそれを使う。
    # 辿れない（--root で content_root を直接指定した等）場合だけ従来どおり親で近似する。
    try:
        repo_root = Project.discover(root).repo_root
    except ProjectError:
        repo_root = root.parent

    warnings: list[str] = []
    errors = validate(root, warnings=warnings, repo_root=repo_root)
    if args.check_urls:
        errors += check_urls(root, warnings=warnings)
    for w in warnings:
        print(w, file=sys.stderr)
    if not errors:
        print("OK")
        sys.exit(0)
    for e in errors:
        print(e)
    sys.exit(1)


if __name__ == "__main__":
    main()
