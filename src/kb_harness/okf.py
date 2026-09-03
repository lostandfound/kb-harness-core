"""Pure renderers for the OKF v0.2 export boundary."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import re
from typing import Any, Mapping

import yaml

from .markdown import parse_document
from .diagnostics import HarnessError


class OkfExportError(ValueError):
    """A source document cannot be rendered as OKF v0.2."""

    def __init__(self, code: str, message: str, *, path: str | None = None) -> None:
        self.code = code
        self.path = path
        super().__init__(message)


_CLAIM_STATUSES = {"proposed", "accepted", "disputed", "rejected"}
_LIFECYCLE_STATUSES = {"draft", "stable", "deprecated"}
_ISO_OFFSET = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")
_DATE_HEADING = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})(?:\s|$)")
_REF_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _normalize_dates(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat(timespec="auto")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, list):
        return [_normalize_dates(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize_dates(item) for key, item in value.items()}
    return value


def _frontmatter(document_path: str, text: str) -> tuple[dict[str, Any], str]:
    try:
        document = parse_document(document_path, text)
    except HarnessError as error:
        raise OkfExportError("okf.document.invalid", str(error), path=document_path) from error
    values = dict(document.frontmatter)
    if not isinstance(values.get("type"), str) or not values["type"].strip():
        raise OkfExportError("okf.type.required", "type must be a non-empty string", path=document_path)
    return values, document.body


def _dump(values: dict[str, Any], body: str, path: str) -> str:
    try:
        header = yaml.safe_dump(
            values,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=True,
        ).rstrip("\n")
    except Exception as error:
        raise OkfExportError("okf.yaml.serialize", str(error), path=path) from error
    return f"---\n{header}\n---\n{body}"


def render_okf_concept(path: str, text: str) -> str:
    """Render one internal concept document as an OKF concept document."""
    values, body = _frontmatter(path, text)
    if "timestamp" in values:
        if "internal_timestamp" in values:
            raise OkfExportError(
                "okf.timestamp.conflict",
                "timestamp and internal_timestamp both exist",
                path=path,
            )
        values["internal_timestamp"] = values.pop("timestamp")
    values = _normalize_dates(values)
    if values.get("type") == "Claim":
        if "claim_status" in values:
            raise OkfExportError("okf.claim_status.conflict", "claim_status already exists", path=path)
        status = values.get("status")
        if status not in _CLAIM_STATUSES:
            raise OkfExportError("okf.claim_status.invalid", "invalid Claim status", path=path)
        values["claim_status"] = status
        values["status"] = "stable"
    return _dump(values, body, path)


def render_okf_index(path: str, text: str, *, root: bool) -> str:
    """Render a root or subdirectory OKF index."""
    if root:
        try:
            document = parse_document(path, text)
        except HarnessError as error:
            raise OkfExportError("okf.document.invalid", str(error), path=path) from error
        return _dump({"okf_version": "0.2"}, document.body, path)
    marker = text.find("\n---\n", 4)
    if text.startswith("---\n") and marker >= 0:
        return text[marker + len("\n---\n") :]
    return text


def _source_values(source: Any, registry: Mapping[str, Any] | None, path: str) -> tuple[dict[str, Any], str | None]:
    if isinstance(source, str):
        if source.startswith("ref:"):
            ref_id = source[4:].strip()
            if _REF_ID.fullmatch(ref_id) is None:
                raise OkfExportError("okf.source.ref_id_invalid", "source reference id is invalid", path=path)
            if not ref_id or registry is None or ref_id not in registry:
                raise OkfExportError("okf.source.ref_not_found", "source reference is not registered", path=path)
            return {"id": ref_id, "resource": f"/references/{ref_id}.md", "title": _reference_title(registry[ref_id], ref_id)}, ref_id
        if source.startswith(("http://", "https://")):
            return {"resource": source}, None
        return {"resource": source}, None
    if not isinstance(source, Mapping):
        raise OkfExportError("okf.source.invalid", "source must be string or mapping", path=path)
    resource = source.get("resource")
    if not isinstance(resource, str) or not resource:
        raise OkfExportError("okf.source.resource_required", "source resource must be non-empty string", path=path)
    return dict(source), None


def _reference_title(entry: Any, ref_id: str) -> str:
    return entry.get("title", ref_id) if isinstance(entry, Mapping) else ref_id


def _load_registry(project_root: Path, path: str) -> Mapping[str, Any]:
    registry_path = project_root / "references.yml"
    if not registry_path.is_file():
        raise OkfExportError("okf.references.missing", "references.yml is required", path=path)
    try:
        registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise OkfExportError("okf.references.invalid", str(error), path=path) from error
    if not isinstance(registry, Mapping):
        raise OkfExportError("okf.references.not_mapping", "references.yml must be a mapping", path=path)
    return registry


def _render_export_concept(path: str, text: str, registry: Mapping[str, Any] | None) -> tuple[str, set[str]]:
    values, body = _frontmatter(path, text)
    used: set[str] = set()
    if "sources" in values:
        sources = values["sources"]
        if not isinstance(sources, list):
            raise OkfExportError("okf.sources.not_list", "sources must be a list", path=path)
        converted = []
        for source in sources:
            converted_source, ref_id = _source_values(source, registry, path)
            converted.append(converted_source)
            if ref_id:
                used.add(ref_id)
        values["sources"] = converted
    return render_okf_concept(path, _dump(values, body, path)), used


def _render_reference(ref_id: str, entry: Any, path: str) -> str:
    if not isinstance(entry, Mapping):
        raise OkfExportError("okf.references.entry_not_mapping", "reference entry must be a mapping", path=path)
    values: dict[str, Any] = {"id": ref_id, "title": _reference_title(entry, ref_id), "type": "Reference"}
    if isinstance(entry.get("url"), str) and entry["url"]:
        values["resource"] = entry["url"]
    if isinstance(entry.get("type"), str) and entry["type"]:
        values["reference_type"] = entry["type"]
    for key, value in entry.items():
        if key not in {"type", "title", "url"}:
            values[key] = value
    return _dump(values, "", path)


def _raw_frontmatter(text: str, path: str) -> tuple[dict[str, Any] | None, str]:
    if not text.startswith("---\n"):
        return None, text
    end = text.find("\n---\n", 4)
    if end < 0:
        raise OkfExportError("okf.document.invalid", "unterminated frontmatter", path=path)
    try:
        values = yaml.safe_load(text[4:end]) or {}
    except yaml.YAMLError as error:
        raise OkfExportError("okf.document.invalid", str(error), path=path) from error
    if not isinstance(values, Mapping):
        raise OkfExportError("okf.document.invalid", "frontmatter must be mapping", path=path)
    return dict(values), text[end + 5 :]


def _validate_timestamp(value: Any, path: str, errors: list[str]) -> None:
    if path.endswith(".stale_after") or path.endswith(".at"):
        valid_datetime = isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None
        valid_string = isinstance(value, str) and _ISO_OFFSET.fullmatch(value) is not None
        if not valid_datetime and not valid_string:
            errors.append(f"{path} must be ISO 8601 with offset")
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key in {"at", "stale_after"}:
                valid_datetime = isinstance(child, datetime) and child.tzinfo is not None and child.utcoffset() is not None
                valid_string = isinstance(child, str) and _ISO_OFFSET.fullmatch(child) is not None
                if not valid_datetime and not valid_string:
                    errors.append(f"{path}.{key} must be ISO 8601 with offset")
            else:
                _validate_timestamp(child, f"{path}.{key}", errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _validate_timestamp(child, f"{path}[{index}]", errors)


def _validate_okf_documents(documents: Mapping[str, str]) -> list[str]:
    errors: list[str] = []
    for path in sorted(documents):
        text = documents[path]
        is_root_index = path == "index.md"
        is_index = Path(path).name == "index.md"
        is_log = Path(path).name == "log.md"
        try:
            values, body = _raw_frontmatter(text, path)
        except OkfExportError as error:
            errors.append(f"{path}: {error.code}")
            continue
        if is_index or is_log:
            if is_root_index:
                if values and (set(values) != {"okf_version"} or values.get("okf_version") != "0.2"):
                    errors.append(f"{path}: root index frontmatter must only declare okf_version: 0.2")
            elif values is not None:
                errors.append(f"{path}: reserved index/log documents must not have frontmatter")
            if is_log:
                for line in body.splitlines():
                    match = _DATE_HEADING.match(line)
                    if match:
                        try:
                            date.fromisoformat(match.group(1))
                        except ValueError:
                            errors.append(f"{path}: invalid log date heading {match.group(1)}")
            continue
        if values is None:
            errors.append(f"{path}: concept document requires frontmatter")
            continue
        if not isinstance(values.get("type"), str) or not values["type"].strip():
            errors.append(f"{path}: type is required and must be non-empty")
        if "timestamp" in values:
            errors.append(f"{path}: okf.legacy_timestamp is not allowed; use generated.at or internal_timestamp")
        sources = values.get("sources")
        if sources is not None:
            if not isinstance(sources, list):
                errors.append(f"{path}: sources must be a list")
            else:
                for index, source in enumerate(sources):
                    if not isinstance(source, Mapping) or not isinstance(source.get("resource"), str) or not source["resource"].strip():
                        errors.append(f"{path}: sources[{index}] must have a non-empty resource")
        if "status" in values and values["status"] not in _LIFECYCLE_STATUSES:
            errors.append(f"{path}: status must be draft, stable, or deprecated")
        for key in ("generated", "verified", "stale_after"):
            if key in values:
                _validate_timestamp(values[key], f"{path}.{key}", errors)
    return sorted(errors)


def validate_okf_bundle(root: Path) -> list[str]:
    """Read-only validation of an OKF v0.2 bundle; returns stable diagnostics."""
    root = Path(root)
    if not root.is_dir():
        return [f"{root}: bundle directory does not exist"]
    documents: dict[str, str] = {}
    for path in sorted(root.rglob("*.md")):
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            try:
                documents[relative] = path.read_text(encoding="utf-8")
            except OSError as error:
                documents[relative] = ""
                documents[relative] = f""
                # Keep diagnostics deterministic while continuing validation.
                documents.pop(relative)
                return [f"{relative}: cannot read document ({error})"]
    return _validate_okf_documents(documents)


def plan_okf_export(project: Any, output_root: Path) -> Mapping[Path, str]:
    """Plan a deterministic, write-free OKF v0.2 export bundle."""
    content_root = Path(project.content_root)
    resolved_output_root = Path(output_root).resolve(strict=False)

    def checked_output_path(path: Path, display_path: str) -> Path:
        try:
            path.resolve(strict=False).relative_to(resolved_output_root)
        except ValueError as error:
            raise OkfExportError("okf.output.outside_root", "output path is outside output root", path=display_path) from error
        return path

    files = []
    for path in content_root.rglob("*.md"):
        if path.is_symlink():
            raise OkfExportError("okf.input.symlink", "Markdown symlink is not allowed", path=path.relative_to(content_root).as_posix())
        if path.is_file():
            files.append(path)
    files.sort(key=lambda p: p.relative_to(content_root).as_posix())
    source_relatives = {path.relative_to(content_root).as_posix() for path in files}
    result: dict[Path, str] = {}
    refs: set[str] = set()
    registry: Mapping[str, Any] | None = None
    for source_path in files:
        relative = source_path.relative_to(content_root)
        output_path = checked_output_path(output_root / relative, relative.as_posix())
        if output_path in result:
            raise OkfExportError("okf.output.collision", "output path collision", path=relative.as_posix())
        text = source_path.read_text(encoding="utf-8")
        if relative.name == "index.md":
            rendered = render_okf_index(relative.as_posix(), text, root=relative.parent == Path("."))
        elif relative.name == "log.md":
            rendered = render_okf_index(relative.as_posix(), text, root=False)
        else:
            if registry is None:
                try:
                    metadata, _ = _frontmatter(relative.as_posix(), text)
                except OkfExportError:
                    metadata = {}
                sources = metadata.get("sources")
                if isinstance(sources, list) and any(
                    isinstance(source, str) and source.startswith("ref:") for source in sources
                ):
                    registry = _load_registry(content_root, relative.as_posix())
            rendered, used = _render_export_concept(relative.as_posix(), text, registry)
            refs.update(used)
        result[output_path] = rendered
    for ref_id in sorted(refs):
        if f"references/{ref_id}.md" in source_relatives:
            raise OkfExportError("okf.output.collision", "output path collision", path=f"references/{ref_id}.md")
        reference_path = checked_output_path(output_root / "references" / f"{ref_id}.md", f"references/{ref_id}.md")
        if reference_path in result:
            raise OkfExportError("okf.output.collision", "output path collision", path=reference_path.as_posix())
        if registry is None or ref_id not in registry:
            raise OkfExportError("okf.source.ref_not_found", "source reference is not registered", path=ref_id)
        result[reference_path] = _render_reference(ref_id, registry[ref_id], reference_path.as_posix())
    ordered = dict(sorted(result.items(), key=lambda item: item[0].relative_to(output_root).as_posix()))
    validation = _validate_okf_documents(
        {path.relative_to(output_root).as_posix(): text for path, text in ordered.items()}
    )
    if validation:
        raise OkfExportError(
            "okf.conformance.failed",
            "OKF v0.2 export failed conformance: " + "; ".join(validation),
        )
    return ordered
