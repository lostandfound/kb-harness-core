#!/usr/bin/env python3
import argparse
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .diagnostics import HarnessError
from .markdown import parse_document
from .ontology import Ontology, validate_claim
from .project import Project, ProjectError


def default_content_root() -> str:
    """Resolve the configured root while preserving the legacy CLI default."""
    last_error: ProjectError | None = None
    for start in (Path.cwd(), Path(__file__).resolve().parents[2]):
        try:
            project = Project.discover(start)
        except ProjectError as error:
            last_error = error
            continue
        return str(project.content_root.relative_to(project.repo_root))
    raise FileNotFoundError(str(last_error)) from last_error

REQUIRED_FIELDS = ["type", "title", "description", "tags", "timestamp"]
LINK_RE = re.compile(r"\]\((/[^)]+\.md)\)")
TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
PERSON_DATE_RE = re.compile(r"^(\d{4}\??|\d{4}頃|不詳)$")
FILENAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*\.md$")
LIST_FIELDS = ("tags", "sources", "relations", "aliases")
TITLE_PAREN_RE = re.compile(r"[（(]")
# 本文インライン出典表記（（出典: ref-id, ref-id））。全角括弧のみ対応。
CITATION_MARKER_RE = re.compile(r"（出典")
CITATION_RE = re.compile(r"（出典:\s*([^（）]*)）")
# LLM 生成時に混入しうるラッパータグ（本文は純 Markdown であり HTML タグを含まない前提）
ARTIFACT_RE = re.compile(r"</?(content|document|file|output|text)>", re.IGNORECASE)

def _load_vocabulary(root: Path):
    vocab_path = root / "vocabulary.yml"
    data = yaml.safe_load(vocab_path.read_text(encoding="utf-8")) or {}
    raw_predicates = data.get("predicates") or {}
    predicates = {}
    for name, val in raw_predicates.items():
        if isinstance(val, dict):
            predicates[name] = {
                "description": val.get("description", ""),
                "domain": val.get("domain") or [],
                "range": val.get("range") or [],
            }
        else:
            predicates[name] = {"description": val, "domain": [], "range": []}
    tags = set(data.get("tags") or [])
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
    """vocabulary.yml の types: セクションを読み込む。

    戻り値は type 名 → {"directory", "extra_fields", "graph"} の辞書。
    types: が定義されていなければ、entity type の体系そのものが
    未定義でありフォールバックの余地が無いため例外を送出する。
    """
    vocab_path = root / "vocabulary.yml"
    data = yaml.safe_load(vocab_path.read_text(encoding="utf-8")) or {}
    raw_types = data.get("types")
    if not raw_types:
        raise ValueError(f"vocabulary.yml に 'types' セクションが定義されていない: {vocab_path}")
    types = {}
    for name, val in raw_types.items():
        val = val or {}
        types[name] = {
            "directory": val.get("directory"),
            "extra_fields": val.get("extra_fields") or [],
            "graph": val.get("graph", True),
            "sections": val.get("sections") or [],
        }
    return types


def _load_references(root: Path):
    """references.yml を読み込み、(refs, errors) を返す。ファイルが無ければ空扱い。"""
    ref_path = root / "references.yml"
    if not ref_path.exists():
        return {}, []
    data = yaml.safe_load(ref_path.read_text(encoding="utf-8")) or {}
    errors: list[str] = []
    for ref_id, entry in data.items():
        if not isinstance(entry, dict):
            errors.append(f"ERROR /references.yml: '{ref_id}' entry must be a mapping")
            continue
        for field in ("type", "title"):
            if not entry.get(field):
                errors.append(f"ERROR /references.yml: '{ref_id}' missing required field '{field}'")
        if entry.get("type") == "web" and not entry.get("url"):
            errors.append(f"ERROR /references.yml: '{ref_id}' type 'web' requires 'url' (type: web)")
        if "lineage" in entry and (not isinstance(entry.get("lineage"), str) or not entry.get("lineage").strip()):
            errors.append(f"ERROR /references.yml: '{ref_id}' の 'lineage' は空でない文字列である必要がある")
        if "pending" in entry and (not isinstance(entry.get("pending"), str) or not entry.get("pending").strip()):
            errors.append(f"ERROR /references.yml: '{ref_id}' の 'pending' は空でない文字列である必要がある")
    return data, errors


def _validate_evals(root: Path, all_paths: set[str]) -> list[str]:
    """evals/rag-eval.yml（リポジトリルート直下、root の外）を検証する。ファイルが無ければ空扱い。"""
    evals_path = root.parent / "evals" / "rag-eval.yml"
    if not evals_path.exists():
        return []
    rel = "/evals/rag-eval.yml"
    data = yaml.safe_load(evals_path.read_text(encoding="utf-8")) or []
    errors: list[str] = []
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


def validate(root: Path, warnings: list[str] | None = None) -> list[str]:
    errors: list[str] = []
    if warnings is None:
        warnings = []
    predicates, vocab_tags = _load_vocabulary(root)
    properties = _load_properties(root)
    ontology = Ontology.from_mapping({"predicates": predicates, "properties": properties})
    types = _load_types(root)
    type_dir_map = {t["directory"]: name for name, t in types.items()}
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

    unknown_dirs = {
        rel.split("/")[1] for rel in all_paths
        if "/" in rel.lstrip("/") and rel.lstrip("/").split("/")[0] not in type_dir_map
    }
    for dirname in sorted(unknown_dirs):
        errors.append(f"ERROR /{dirname}: 未知のトップレベルディレクトリに .md ファイルが存在する")

    errors.extend(_validate_evals(root, all_paths))

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

        timestamp = fm.get("timestamp")
        if isinstance(timestamp, str) and not TIMESTAMP_RE.match(timestamp):
            errors.append(f"ERROR {rel}: timestamp の形式が不正 '{timestamp}'")

        for field in LIST_FIELDS:
            value = fm.get(field)
            if value is not None and not isinstance(value, list):
                errors.append(f"ERROR {rel}: '{field}' はリスト型である必要がある")

        title = fm.get("title")
        if isinstance(title, str) and TITLE_PAREN_RE.search(title):
            errors.append(f"ERROR {rel}: title に括弧を含めてはならない '{title}'")

        aliases = fm.get("aliases")
        if isinstance(aliases, list):
            for alias in aliases:
                if not isinstance(alias, str) or not alias.strip():
                    errors.append(f"ERROR {rel}: aliases に空文字を含めてはならない")
                elif alias == title:
                    errors.append(f"ERROR {rel}: aliases '{alias}' が自身の title と重複している")

        entity_type = fm.get("type")
        if not is_index:
            sources = fm.get("sources")
            if not sources:
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

        type_def = types.get(entity_type)
        for field in (type_def or {}).get("extra_fields", []):
            value = fm.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"ERROR {rel}: missing required field '{field}'")
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

        for link in LINK_RE.findall(body or ""):
            if link not in all_paths:
                errors.append(f"ERROR {rel}: broken link '{link}'")

        if is_index and path.parent != root:
            linked = set(LINK_RE.findall(body or ""))
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
            linked = set(LINK_RE.findall(body or ""))
            for missing in expected_index_links - linked:
                errors.append(f"ERROR {rel}: ルート index に必須カテゴリリンク欠落 '{missing}'")

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

    pending_unreferenced_count = 0
    for ref_id, entry in references.items():
        pending = entry.get("pending") if isinstance(entry, dict) else None
        if ref_id not in used_references:
            if pending:
                # pending は「実見待ち等で先行登録した」意図的な未参照なので、個別 WARNING ではなく件数集計にまとめる
                pending_unreferenced_count += 1
            else:
                warnings.append(f"WARNING /references.yml: '{ref_id}' はどのエンティティからも参照されていない")
        elif pending:
            warnings.append(
                f"WARNING /references.yml: '{ref_id}' は pending だが参照されている（解除忘れの可能性）"
            )
    if pending_unreferenced_count:
        warnings.append(
            f"INFO references.yml: pending の未参照エントリ {pending_unreferenced_count} 件（意図的未参照）"
        )

    return errors


# urllib デフォルト UA は Wikipedia 等にボット扱いで 403 拒否されるため明示する
_UA = {"User-Agent": "kb-harness-validator/1.0 (+https://github.com/lostandfound/okinawa-karate-book)"}


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


def check_urls(root: Path) -> list[str]:
    errors: list[str] = []
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
            if not _url_reachable(source):
                errors.append(f"ERROR {rel}: unreachable URL {source}")

    references, _ref_errors = _load_references(root)
    for ref_id, entry in references.items():
        if not isinstance(entry, dict):
            continue
        url = entry.get("url")
        doi = entry.get("doi")
        if doi:
            doi_url = f"https://doi.org/{doi}"
            if not _url_reachable(doi_url):
                errors.append(f"ERROR /references.yml: unreachable DOI {doi_url} ({ref_id})")
        elif url:
            if not _url_reachable(url):
                errors.append(f"ERROR /references.yml: unreachable URL {url} ({ref_id})")
    return errors


def fix_timestamps(root: Path) -> list[Path]:
    root = root.resolve()
    toplevel = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, cwd=str(root), check=True,
    ).stdout.strip()
    repo_root = Path(toplevel).resolve()

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
    parser.add_argument("--root", default=default_content_root())
    parser.add_argument("--fix-timestamps", action="store_true")
    parser.add_argument("--check-urls", action="store_true")
    args = parser.parse_args()

    root = Path(args.root)
    if args.fix_timestamps:
        fixed = fix_timestamps(root)
        for path in fixed:
            print(f"fixed timestamp: {path}")

    warnings: list[str] = []
    errors = validate(root, warnings=warnings)
    if args.check_urls:
        errors += check_urls(root)
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
