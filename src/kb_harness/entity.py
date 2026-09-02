"""Entity creation plans and the legacy scaffold API."""

from __future__ import annotations

import os
import re
import shutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

SECTIONS_BY_TYPE = {
    "Person": ["概要", "生涯", "系譜（師と弟子）", "功績"],
    "Style": ["概要", "特徴", "主要人物", "代表的な型"],
    "Kata": ["概要", "由来", "特徴", "伝承する流派"],
    "Term": ["概要", "詳細", "関連項目"],
    "HistoricalEvent": ["概要", "詳細", "関連項目"],
    "Note": ["概要", "本文", "関連項目"],
}
DEFAULT_SECTIONS = ["概要", "詳細", "関連項目"]
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class EntitySpecError(ValueError):
    """A user-correctable entity spec error."""

    def __init__(self, message: str, *, code: str = "entity.spec.invalid", argument: bool = False):
        super().__init__(message)
        self.code = code
        self.argument = argument


@dataclass(frozen=True)
class EntityPlan:
    changes: dict[Path, str]
    diff: str


def _load_types(root: Path) -> dict[str, dict[str, object]]:
    vocabulary_path = root / "vocabulary.yml"
    data = yaml.safe_load(vocabulary_path.read_text(encoding="utf-8")) or {}
    raw_types = data.get("types") if isinstance(data, dict) else None
    if not isinstance(raw_types, dict):
        return {}
    types: dict[str, dict[str, object]] = {}
    for name, definition in raw_types.items():
        if not isinstance(name, str) or not isinstance(definition, dict):
            continue
        types[name] = {
            "directory": definition.get("directory"),
            "extra_fields": definition.get("extra_fields") or [],
            "sections": definition.get("sections") or [],
            "graph": definition.get("graph", True),
        }
    return types


def _nonempty_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EntitySpecError(f"{name} must be a non-empty string")
    return value.strip()


def _string_list(value: object, name: str, *, required: bool = False) -> list[str]:
    if not isinstance(value, list) or (required and not value):
        detail = "non-empty list" if required else "list"
        raise EntitySpecError(f"{name} must be a {detail}")
    return [_nonempty_string(item, f"{name} entries") for item in value]


def _timestamp(value: object, name: str) -> str:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        candidate = value.strip()
        if candidate.endswith("Z"):
            candidate = candidate[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError as error:
            raise EntitySpecError(f"{name} must be an UTC timestamp (ISO-8601)") from error
        if parsed.tzinfo is None:
            raise EntitySpecError(f"{name} must include a timezone")
    else:
        raise EntitySpecError(f"{name} must be an UTC timestamp (ISO-8601)")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _resolve_timestamp(spec_value: object | None, explicit: str | None, clock: Callable[[], datetime] | None) -> str:
    if explicit is not None:
        try:
            return _timestamp(explicit, "--timestamp")
        except EntitySpecError as error:
            raise EntitySpecError(str(error), code=error.code, argument=True) from error
    if spec_value is not None:
        try:
            return _timestamp(spec_value, "timestamp")
        except EntitySpecError as error:
            raise EntitySpecError(str(error), code=error.code, argument=True) from error
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch is not None:
        try:
            value = datetime.fromtimestamp(int(epoch), tz=timezone.utc)
        except (ValueError, OverflowError, OSError) as error:
            raise EntitySpecError("SOURCE_DATE_EPOCH must be an integer Unix timestamp", argument=True) from error
        return value.strftime("%Y-%m-%dT%H:%M:%SZ")
    return _timestamp((clock or (lambda: datetime.now(timezone.utc)))(), "clock")


def load_entity_spec(path: Path) -> dict[str, Any]:
    """Load and perform schema-level checks on an entity YAML spec."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise EntitySpecError(f"spec not found: {path}", code="entity.spec.not_found", argument=True) from error
    except (OSError, yaml.YAMLError) as error:
        raise EntitySpecError(f"cannot read spec {path}: {error}", argument=True) from error
    if not isinstance(data, dict):
        raise EntitySpecError("entity spec must be a YAML mapping", argument=True)
    required = {"type", "slug", "title", "description", "tags", "sources", "sections"}
    optional = {"aliases", "relations", "fields", "timestamp"}
    unknown = sorted(set(data) - required - optional)
    if unknown:
        raise EntitySpecError(f"unknown spec field(s): {', '.join(unknown)}", argument=True)
    missing = sorted(required - set(data))
    if missing:
        raise EntitySpecError(f"missing required spec field(s): {', '.join(missing)}", argument=True)
    _nonempty_string(data["type"], "type")
    slug = _nonempty_string(data["slug"], "slug")
    if not SLUG_RE.fullmatch(slug):
        raise EntitySpecError("slug must be lowercase ASCII kebab-case")
    title = _nonempty_string(data["title"], "title")
    if "（" in title or "(" in title:
        raise EntitySpecError("title must not contain parentheses")
    _nonempty_string(data["description"], "description")
    _string_list(data["tags"], "tags", required=True)
    _string_list(data["sources"], "sources", required=True)
    if "aliases" in data:
        _string_list(data["aliases"], "aliases")
    if "relations" in data:
        if not isinstance(data["relations"], list):
            raise EntitySpecError("relations must be a list")
        if any(not isinstance(relation, dict) for relation in data["relations"]):
            raise EntitySpecError("relations entries must be mappings")
    if "fields" in data and not isinstance(data["fields"], dict):
        raise EntitySpecError("fields must be a mapping")
    if not isinstance(data["sections"], dict):
        raise EntitySpecError("sections must be a mapping")
    for heading, body in data["sections"].items():
        if not isinstance(heading, str) or not heading.strip() or not isinstance(body, str) or not body.strip():
            raise EntitySpecError("sections must map non-empty headings to non-empty text")
    return data


def _frontmatter_and_body(root: Path, spec: Mapping[str, Any], *, timestamp: str) -> tuple[Path, str]:
    try:
        types = _load_types(root)
    except (OSError, yaml.YAMLError) as error:
        raise EntitySpecError(f"cannot load vocabulary.yml: {error}", argument=True) from error
    if not types:
        raise EntitySpecError("vocabulary.yml has no types", argument=True)
    type_key = _nonempty_string(spec["type"], "type")
    matches = {name.lower(): name for name in types}
    entity_type = matches.get(type_key.lower())
    if entity_type is None:
        raise EntitySpecError(f"unknown type '{type_key}'")
    definition = types[entity_type]
    directory = definition.get("directory")
    if not isinstance(directory, str) or not directory:
        raise EntitySpecError(f"type '{entity_type}' has no valid directory", argument=True)
    path = root / directory / f"{spec['slug']}.md"
    if path.exists():
        raise EntitySpecError(f"entity already exists: {path}", code="entity.duplicate")

    configured_sections = definition.get("sections") or SECTIONS_BY_TYPE.get(entity_type) or DEFAULT_SECTIONS
    if not isinstance(configured_sections, list) or not all(isinstance(item, str) and item for item in configured_sections):
        raise EntitySpecError(f"type '{entity_type}' has invalid sections configuration", argument=True)
    supplied_sections = spec["sections"]
    if set(supplied_sections) != set(configured_sections) or len(supplied_sections) != len(configured_sections):
        missing = [item for item in configured_sections if item not in supplied_sections]
        extra = [item for item in supplied_sections if item not in configured_sections]
        detail = []
        if missing:
            detail.append(f"missing sections: {', '.join(missing)}")
        if extra:
            detail.append(f"unknown sections: {', '.join(extra)}")
        raise EntitySpecError("section layout mismatch (" + "; ".join(detail) + ")")

    extra_fields = definition.get("extra_fields") or []
    if not isinstance(extra_fields, list) or not all(isinstance(item, str) for item in extra_fields):
        raise EntitySpecError(f"type '{entity_type}' has invalid extra_fields configuration", argument=True)
    fields = spec.get("fields") or {}
    unknown_fields = sorted(set(fields) - set(extra_fields))
    if unknown_fields:
        raise EntitySpecError(f"unknown field(s): {', '.join(unknown_fields)}")
    for field in extra_fields:
        if field not in fields or not isinstance(fields[field], str) or not fields[field].strip():
            raise EntitySpecError(f"missing required field '{field}'")

    frontmatter: dict[str, object] = {
        "type": entity_type,
        "title": _nonempty_string(spec["title"], "title"),
        "description": _nonempty_string(spec["description"], "description"),
        "tags": _string_list(spec["tags"], "tags", required=True),
        "timestamp": timestamp,
        "sources": _string_list(spec["sources"], "sources", required=True),
    }
    if "aliases" in spec:
        frontmatter["aliases"] = _string_list(spec["aliases"], "aliases")
    if "relations" in spec:
        frontmatter["relations"] = spec["relations"]
    for field in extra_fields:
        frontmatter[field] = fields[field].strip()
    rendered = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False, default_flow_style=False).rstrip()
    # Keep the repository's canonical, unquoted UTC timestamp spelling.
    rendered = re.sub(r"(?m)^timestamp: ['\"]([^'\"]+)['\"]$", r"timestamp: \1", rendered)
    body = "\n\n".join(f"## {heading}\n\n{str(supplied_sections[heading]).strip()}" for heading in configured_sections)
    return path, f"---\n{rendered}\n---\n\n{body}\n"


def plan_entity_create(project: Any, spec_path: Path, *, timestamp: str | None = None, clock: Callable[[], datetime] | None = None) -> EntityPlan:
    """Build and fully validate a create plan without touching the real KB."""
    spec = load_entity_spec(spec_path)
    resolved_timestamp = _resolve_timestamp(spec.get("timestamp"), timestamp, clock)
    entity_path, entity_text = _frontmatter_and_body(project.content_root, spec, timestamp=resolved_timestamp)
    from .staging import stage_and_validate
    from .sync import unified_diff

    changes = stage_and_validate(
        project, entity_path, entity_text, prefix="kb-entity-",
        validation_error=lambda details: EntitySpecError("new entity failed full validation: " + details, code="entity.validation.failed"),
        sync_error=lambda: EntitySpecError("new entity leaves index/graph synchronization changes", code="entity.sync.failed"),
        copytree=shutil.copytree,
    )
    return EntityPlan(changes=changes, diff=unified_diff(changes, display_root=project.repo_root))


def create_entity(root: Path, type_key: str, slug: str, *, clock: Callable[[], datetime] | None = None) -> Path:
    """Legacy TODO scaffold retained for ``scripts/new_entity.py``."""
    types = _load_types(root)
    type_map = {name.lower(): (definition["directory"], name) for name, definition in types.items() if isinstance(definition.get("directory"), str)}
    if type_key not in type_map:
        raise ValueError(f"unknown type '{type_key}' (expected one of {sorted(type_map)})")
    dirname, entity_type = type_map[type_key]
    path = root / dirname / f"{slug}.md"
    if path.exists():
        raise ValueError(f"entity already exists: {path}")
    current_time = (clock or (lambda: datetime.now(timezone.utc)))()
    now = current_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    section_names = types[entity_type]["sections"] or SECTIONS_BY_TYPE.get(entity_type) or DEFAULT_SECTIONS
    sections = "\n".join(f"## {name}\n\nTODO\n" for name in section_names)
    extra_fields = "".join(f"{field}: TODO\n" for field in types[entity_type]["extra_fields"])
    text = ("---\n" f"type: {entity_type}\n" "title: TODO\n" "description: TODO\n" "tags: []\n" "aliases: []\n" f"timestamp: {now}\n" "sources:\n" "  - TODO\n" f"{extra_fields}" "---\n\n" f"{sections}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path
