"""Local reference registry health checks and deterministic creation."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import yaml
import re

from .sync import unified_diff


class ReferenceSpecError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _reference_id(item: dict[str, Any], authors: list[str], year: str) -> str:
    """Choose a stable identifier, honoring an explicit search-result id."""
    explicit_id = str(item.get("id", "")).strip()
    if explicit_id:
        return explicit_id
    first_author = authors[0] if authors else "ref"
    base = re.sub(r"[^a-z0-9]+", "-", first_author.lower()).strip("-") or "ref"
    if year:
        return f"{base}-{year}"
    return base


def reference_spec_from_search(source_path: Path) -> dict[str, Any]:
    """Convert one JSON/YAML search result into a ``reference create`` spec."""
    try:
        raw = yaml.safe_load(source_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ReferenceSpecError("search.result.read", str(exc)) from exc
    items = raw.get("results", raw.get("items", raw)) if isinstance(raw, dict) else raw
    if not isinstance(items, list) or not items:
        raise ReferenceSpecError("search.results.empty", "search result contains no results")
    item = items[0]
    if not isinstance(item, dict):
        raise ReferenceSpecError("search.result.mapping", "search result must contain mappings")
    title = str(item.get("title", "")).strip()
    if not title:
        raise ReferenceSpecError("search.result.title", "search result requires title")
    authors = item.get("authors", item.get("author", []))
    if isinstance(authors, str):
        authors = [authors]
    authors = [str(a).strip() for a in authors if str(a).strip()] if isinstance(authors, list) else []
    year = str(item.get("year", "")).strip()
    url = str(item.get("url", "")).strip()
    ref_id = _reference_id(item, authors, year)
    result: dict[str, Any] = {"id": ref_id, "type": item.get("type", "journal-article" if item.get("venue") else "book"), "title": title}
    if authors: result["author"] = "、".join(authors)
    for key in ("publisher", "venue", "year", "url"):
        if item.get(key): result[key] = item[key]
    return result


@dataclass(frozen=True)
class ReferencePlan:
    changes: dict[Path, str]
    diff: str = ""


def plan_reference_create(path: Path, spec_path: Path) -> ReferencePlan:
    try:
        spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ReferenceSpecError("reference.spec.read", str(exc)) from exc
    if not isinstance(spec, dict):
        raise ReferenceSpecError("reference.spec.mapping", "reference spec must be a mapping")
    ref_id = spec.pop("id", None)
    if not isinstance(ref_id, str) or not ref_id.strip():
        raise ReferenceSpecError("reference.missing.id", "reference spec requires id")
    if not spec.get("type"):
        raise ReferenceSpecError("reference.missing.type", f"{ref_id}: missing type")
    if not spec.get("title"):
        raise ReferenceSpecError("reference.missing.title", f"{ref_id}: missing title")
    if spec.get("url") and not str(spec["url"]).startswith(("http://", "https://")):
        raise ReferenceSpecError("reference.url.invalid", f"{ref_id}: URL must start with http:// or https://")
    try:
        # Preserve the registry's original bytes (including comments, quoting,
        # ordering, line endings, and blank lines) instead of round-tripping it.
        existing_text = path.read_bytes().decode("utf-8") if path.exists() else ""
        data = yaml.safe_load(existing_text) if path.exists() else {}
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ReferenceSpecError("reference.read", str(exc)) from exc
    if not isinstance(data, dict):
        raise ReferenceSpecError("reference.root.mapping", "references.yml must be a mapping")
    if ref_id in data:
        raise ReferenceSpecError("reference.duplicate.id", f"{ref_id}: duplicate reference id")

    # Only the new top-level entry is canonicalized.  The sole normalization
    # permitted on existing content is adding one separator when a non-empty
    # file has no line terminator; existing trailing blank lines remain
    # untouched.  A pure CRLF file keeps CRLF for the appended block too.
    newline = (
        "\r\n"
        if "\r\n" in existing_text
        and "\n" not in existing_text.replace("\r\n", "")
        else "\n"
    )
    entry_text = yaml.safe_dump(
        {ref_id: spec}, allow_unicode=True, sort_keys=False
    ).replace("\n", newline)
    if data == {}:
        # ``{}`` is a valid empty registry, but appending after its document
        # would create two adjacent top-level documents.  Replace that empty
        # representation with the first entry (comments-only/empty documents
        # still fail the root-mapping check above).
        new_text = entry_text
    else:
        separator = newline if existing_text and not existing_text.endswith(newline) else ""
        new_text = existing_text + separator + entry_text

    # Validate the actual bytes that will be written, including the new entry.
    # This guards against producing a plan whose appended block is not a valid
    # top-level mapping without reparsing/reformatting the existing registry.
    try:
        validated = yaml.safe_load(new_text)
    except yaml.YAMLError as exc:
        raise ReferenceSpecError("reference.write.invalid", str(exc)) from exc
    if (
        not isinstance(validated, dict)
        or ref_id not in validated
        or validated[ref_id] != spec
    ):
        raise ReferenceSpecError(
            "reference.write.invalid",
            f"{ref_id}: appended reference could not be validated",
        )

    changes = {path: new_text}
    return ReferencePlan(changes, diff=unified_diff(changes))

class _Loader(yaml.SafeLoader):
    pass

_duplicate_ids: list[str] = []
def _mapping(loader, node, deep=False):
    seen = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:
            _duplicate_ids.append(str(key))
        seen.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep)
_Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)

def reference_health(path: Path) -> dict[str, Any]:
    try:
        _duplicate_ids.clear()
        data = yaml.load(path.read_text(encoding="utf-8"), Loader=_Loader)
    except (OSError, yaml.YAMLError) as exc:
        return {"ok": False, "diagnostics": [{"code": "reference.read", "message": str(exc)}]}
    if not isinstance(data, dict):
        return {"ok": False, "diagnostics": [{"code": "reference.root.mapping", "message": "references.yml must be a mapping"}]}
    diagnostics = []
    for ref_id in sorted(set(_duplicate_ids)):
        diagnostics.append({"code": "reference.duplicate.id", "message": f"{ref_id}: duplicate reference id"})
    for ref_id in sorted(data, key=str):
        entry = data[ref_id]
        if not isinstance(entry, dict):
            diagnostics.append({"code": "reference.entry.mapping", "message": f"{ref_id}: entry must be a mapping"}); continue
        if not entry.get("type"):
            diagnostics.append({"code": "reference.missing.type", "message": f"{ref_id}: missing type"})
        if not entry.get("url") and not (entry.get("title") and (entry.get("author") or entry.get("publisher"))):
            diagnostics.append({"code": "reference.missing.url_or_bibliography", "message": f"{ref_id}: requires url or bibliography"})
        if entry.get("url") and not str(entry["url"]).startswith(("http://", "https://")):
            diagnostics.append({"code": "reference.url.invalid", "message": f"{ref_id}: URL must use http or https"})
    return {"ok": not diagnostics, "diagnostics": diagnostics, "count": len(data)}


# ---------------------------------------------------------------------------
# 照会（show / search）
#
# エージェントが references.yml を丸ごと文脈に読み込まずに済むよう、ID・語句・
# エンティティ単位で必要なエントリだけを取り出す。索引は持たず、毎回レジストリを
# 読み直す（数百〜数千件なら十分速く、決定性を保てる）。
# ---------------------------------------------------------------------------

SEARCH_FIELDS = ("id", "title", "author", "publisher", "journal", "url", "doi", "note", "lineage")
SUMMARY_FIELDS = ("type", "title", "author", "year", "url")

_CITATION_RE = re.compile(r"（出典:\s*([^（）]*)）")


def load_references(path: Path) -> dict[str, dict[str, Any]]:
    """references.yml を読み、ID → エントリの mapping を返す。"""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ReferenceSpecError("reference.read", str(exc)) from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ReferenceSpecError("reference.root.mapping", "references.yml must be a mapping")
    return {str(k): (v if isinstance(v, dict) else {}) for k, v in data.items()}


def normalize_url(url: str) -> str:
    """重複判定用に URL を正規化する（scheme・www・末尾スラッシュ・fragment の揺れを吸収）。"""
    value = str(url).strip()
    value = re.sub(r"^https?://", "", value, flags=re.IGNORECASE)
    value = re.sub(r"^www\.", "", value, flags=re.IGNORECASE)
    value = value.split("#", 1)[0]
    return value.rstrip("/").lower()


def normalize_doi(doi: str) -> str:
    value = str(doi).strip()
    value = re.sub(r"^https?://(dx\.)?doi\.org/", "", value, flags=re.IGNORECASE)
    value = re.sub(r"^doi:\s*", "", value, flags=re.IGNORECASE)
    return value.lower()


def _entry_with_id(ref_id: str, entry: dict[str, Any]) -> dict[str, Any]:
    return {"id": ref_id, **entry}


def entity_reference_ids(entity_path: Path) -> list[str]:
    """エンティティの ``sources`` と本文の ``（出典: id）`` から参照 ID を初出順に集める。"""
    from .markdown import parse_document
    from .diagnostics import HarnessError

    try:
        text = entity_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ReferenceSpecError("reference.entity.read", str(exc)) from exc
    try:
        document = parse_document(str(entity_path), text)
    except HarnessError as exc:
        raise ReferenceSpecError("reference.entity.frontmatter", exc.diagnostic.message) from exc
    ids: list[str] = []

    def _add(ref_id: str) -> None:
        ref_id = ref_id.strip()
        if ref_id and ref_id not in ids:
            ids.append(ref_id)

    sources = document.frontmatter.get("sources")
    if isinstance(sources, list):
        for source in sources:
            if isinstance(source, str) and source.startswith("ref:"):
                _add(source[len("ref:"):])
    for match in _CITATION_RE.finditer(document.body):
        for token in match.group(1).split(","):
            token = token.strip()
            if token.startswith("ref:"):
                token = token[len("ref:"):]
            _add(token)
    return ids


def reference_show(path: Path, ids: list[str]) -> dict[str, Any]:
    """ID を指定してエントリを返す。見つからない ID は ``missing`` と診断に載る。"""
    registry = load_references(path)
    entries = [_entry_with_id(ref_id, registry[ref_id]) for ref_id in ids if ref_id in registry]
    missing = [ref_id for ref_id in ids if ref_id not in registry]
    diagnostics = [{"code": "reference.id.missing", "message": f"{ref_id}: reference id not found"} for ref_id in missing]
    return {"ok": not missing, "entries": entries, "missing": missing, "diagnostics": diagnostics}


def reference_show_for_entity(references_path: Path, entity_path: Path) -> dict[str, Any]:
    """エンティティが引く出典の書誌をまとめて返す。"""
    ids = entity_reference_ids(entity_path)
    result = reference_show(references_path, ids)
    result["entity"] = str(entity_path)
    result["ids"] = ids
    return result


def reference_search(
    path: Path,
    terms: list[str],
    *,
    fields: tuple[str, ...] | None = None,
    url: str | None = None,
    doi: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """語句（部分一致・大小無視・AND）と URL / DOI（正規化後の完全一致）でエントリを探す。

    ``terms`` ``url`` ``doi`` を複数与えたときは全条件を満たすものだけを返す。
    結果はレジストリの記載順で、順序は入力に対して決定的である。
    """
    registry = load_references(path)
    search_fields = fields or SEARCH_FIELDS
    lowered = [t.lower() for t in terms if t.strip()]
    want_url = normalize_url(url) if url else None
    want_doi = normalize_doi(doi) if doi else None
    hits: list[dict[str, Any]] = []
    for ref_id, entry in registry.items():
        if want_url is not None and normalize_url(str(entry.get("url", ""))) != want_url:
            continue
        if want_doi is not None:
            candidates = [str(entry.get("doi", ""))]
            if entry.get("url"):
                candidates.append(str(entry["url"]))
            if not any(normalize_doi(c) == want_doi for c in candidates if c):
                continue
        if lowered:
            haystack = " ".join(
                (ref_id if f == "id" else str(entry.get(f, ""))) for f in search_fields
            ).lower()
            if not all(term in haystack for term in lowered):
                continue
        hits.append(_entry_with_id(ref_id, entry))
    total = len(hits)
    if limit is not None:
        hits = hits[: max(limit, 0)]
    return {"ok": True, "entries": hits, "count": total, "shown": len(hits)}


def format_reference_line(entry: dict[str, Any]) -> str:
    """text 出力用の 1 行要約（id・type・title・author・year・url）。"""
    parts = [entry.get("id", "")]
    for field in SUMMARY_FIELDS:
        value = entry.get(field)
        if value not in (None, ""):
            parts.append(str(value))
    return "\t".join(str(p) for p in parts)


def format_reference_block(entry: dict[str, Any]) -> str:
    """text 出力用の全フィールド表示（YAML）。"""
    ref_id = entry.get("id", "")
    body = {k: v for k, v in entry.items() if k != "id"}
    return yaml.safe_dump({ref_id: body}, allow_unicode=True, sort_keys=False)
