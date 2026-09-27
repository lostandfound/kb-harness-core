"""Local reference registry health checks and deterministic creation."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import yaml
import re

from .sync import unified_diff


class ReferenceSpecError(ValueError):
    """A reference spec/registry error.

    ``argument`` marks a problem with how the command was invoked or with the
    surrounding configuration (unreadable spec/registry, malformed registry
    root) as opposed to a content problem in the reference itself (missing
    field, bad URL, duplicate id), mirroring ``EntitySpecError``.
    """

    def __init__(self, code: str, message: str, *, argument: bool = False):
        super().__init__(message)
        self.code = code
        self.argument = argument


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


def check_reference_entry(ref_id: str, entry: Any) -> list[dict[str, str]]:
    """1 エントリを検査し、構造化診断（`code` / `message`）のリストを返す。

    ``references.yml`` の per-entry 検査規則はここに 1 つだけ持ち、
    ``validate`` / ``kb reference health`` / ``kb reference create`` の
    3 つの入口が全てこの関数を呼ぶ。規則:

    - `type` / `title` は必須。
    - `url` があれば `http://` / `https://` で始まること。
    - `type: web` は `url` が必須（書誌情報では代替できない）。
    - それ以外の型は `url` か、書誌情報（`title` に加え `author` か
      `publisher` のどちらか）のいずれかが必要。
    - `lineage` / `pending` はキーがあれば非空文字列であること。
    """
    if not isinstance(entry, dict):
        return [{"code": "reference.entry.mapping", "message": f"{ref_id}: entry must be a mapping"}]

    diagnostics: list[dict[str, str]] = []
    for field in ("type", "title"):
        if not entry.get(field):
            diagnostics.append({"code": f"reference.missing.{field}", "message": f"{ref_id}: missing required field '{field}'"})

    url = entry.get("url")
    if url and not str(url).startswith(("http://", "https://")):
        diagnostics.append({"code": "reference.url.invalid", "message": f"{ref_id}: URL must start with http:// or https://"})

    if entry.get("type") == "web":
        if not url:
            diagnostics.append({"code": "reference.missing.url", "message": f"{ref_id}: type 'web' requires 'url'"})
    elif not url and not (entry.get("title") and (entry.get("author") or entry.get("publisher"))):
        diagnostics.append({
            "code": "reference.missing.url_or_bibliography",
            "message": f"{ref_id}: requires 'url' or bibliography ('title' に加え 'author' か 'publisher')",
        })

    for field in ("lineage", "pending"):
        if field in entry and (not isinstance(entry.get(field), str) or not entry.get(field).strip()):
            diagnostics.append({
                "code": f"reference.{field}.invalid",
                "message": f"{ref_id}: '{field}' は空でない文字列である必要がある",
            })

    return diagnostics


def _parse_registry(text: str) -> tuple[dict[str, Any], list[str]]:
    """レジストリのテキストから (data, duplicate_ids) を得る。

    重複検出はルート mapping 直下のキーだけを見る。1 エントリ内で
    `author:` を 2 回書くような入れ子の mapping の重複は対象外
    （PyYAML の SafeLoader は後勝ちで解決する）。
    """
    try:
        loader = yaml.SafeLoader(text)
    except yaml.YAMLError as exc:
        raise ReferenceSpecError("reference.read", str(exc), argument=True) from exc
    try:
        root_node = loader.get_single_node()
        duplicate_ids: list[str] = []
        if isinstance(root_node, yaml.MappingNode):
            seen: set[Any] = set()
            for key_node, _value_node in root_node.value:
                key = loader.construct_object(key_node, deep=True)
                if key in seen:
                    duplicate_ids.append(str(key))
                seen.add(key)
    except yaml.YAMLError as exc:
        raise ReferenceSpecError("reference.read", str(exc), argument=True) from exc
    finally:
        loader.dispose()

    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise ReferenceSpecError("reference.read", str(exc), argument=True) from exc
    if not isinstance(data, dict):
        raise ReferenceSpecError("reference.root.mapping", "references.yml must be a mapping", argument=True)
    return data, sorted(set(duplicate_ids), key=str)


def load_registry(path: Path) -> tuple[dict[str, Any], list[str]]:
    """``references.yml`` を読み込み (data, duplicate_ids) を返す。

    ファイルが無ければ空のレジストリ ``({}, [])`` として扱う。読み込み・
    構文エラーおよびルートが mapping でない場合は ``ReferenceSpecError``
    を送出する（呼び出し側がそれぞれの契約に翻訳する）。
    """
    if not path.exists():
        return {}, []
    try:
        text = path.read_bytes().decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise ReferenceSpecError("reference.read", str(exc), argument=True) from exc
    return _parse_registry(text)


def plan_reference_create(path: Path, spec_path: Path) -> ReferencePlan:
    try:
        spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ReferenceSpecError("reference.spec.read", str(exc), argument=True) from exc
    if not isinstance(spec, dict):
        raise ReferenceSpecError("reference.spec.mapping", "reference spec must be a mapping", argument=True)
    ref_id = spec.pop("id", None)
    if not isinstance(ref_id, str) or not ref_id.strip():
        raise ReferenceSpecError("reference.missing.id", "reference spec requires id")

    # Preserve the registry's original bytes (including comments, quoting,
    # ordering, line endings, and blank lines) instead of round-tripping it.
    try:
        existing_text = path.read_bytes().decode("utf-8") if path.exists() else ""
    except (OSError, UnicodeError) as exc:
        raise ReferenceSpecError("reference.read", str(exc), argument=True) from exc
    data, _existing_duplicate_ids = _parse_registry(existing_text)
    if ref_id in data:
        raise ReferenceSpecError("reference.duplicate.id", f"{ref_id}: duplicate reference id")

    # 既存レジストリの重複は construct 済みの data からは分からないため、あくまで
    # 新規 ID の衝突だけをここで見る。全エントリの検査規則（type/title/url/
    # 書誌情報など）は validate / health と共通の check_reference_entry に譲る。
    diagnostics = check_reference_entry(ref_id, spec)
    if diagnostics:
        first = diagnostics[0]
        raise ReferenceSpecError(first["code"], first["message"])

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
        raise ReferenceSpecError("reference.write.invalid", str(exc), argument=True) from exc
    if (
        not isinstance(validated, dict)
        or ref_id not in validated
        or validated[ref_id] != spec
    ):
        raise ReferenceSpecError(
            "reference.write.invalid",
            f"{ref_id}: appended reference could not be validated",
            argument=True,
        )

    changes = {path: new_text}
    return ReferencePlan(changes, diff=unified_diff(changes))

def reference_health(path: Path) -> dict[str, Any]:
    """``references.yml`` の構造を検査する。

    per-entry の規則は ``check_reference_entry`` に、読み込みと重複検出
    （ルート mapping 直下のキーのみ）は ``load_registry`` に委ねる。
    """
    try:
        data, duplicate_ids = load_registry(path)
    except ReferenceSpecError as error:
        return {"ok": False, "diagnostics": [{"code": error.code, "message": str(error)}]}
    diagnostics: list[dict[str, str]] = [
        {"code": "reference.duplicate.id", "message": f"{ref_id}: duplicate reference id"}
        for ref_id in duplicate_ids
    ]
    for ref_id in sorted(data, key=str):
        diagnostics.extend(check_reference_entry(ref_id, data[ref_id]))
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
    """references.yml を読み、ID → エントリの mapping を返す。読み込みは ``load_registry`` に委ねる。"""
    data, _duplicate_ids = load_registry(path)
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
