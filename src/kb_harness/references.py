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
