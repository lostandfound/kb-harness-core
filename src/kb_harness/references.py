"""Local reference registry health checks and deterministic creation."""
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import yaml


class ReferenceSpecError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ReferencePlan:
    changes: dict[Path, str]


def plan_reference_create(path: Path, spec_path: Path) -> ReferencePlan:
    try:
        spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
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
        data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, yaml.YAMLError) as exc:
        raise ReferenceSpecError("reference.read", str(exc)) from exc
    if not isinstance(data, dict):
        raise ReferenceSpecError("reference.root.mapping", "references.yml must be a mapping")
    if ref_id in data:
        raise ReferenceSpecError("reference.duplicate.id", f"{ref_id}: duplicate reference id")
    data[ref_id] = spec
    return ReferencePlan({path: yaml.safe_dump(dict(sorted(data.items())), allow_unicode=True, sort_keys=False)})

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
