"""Local reference registry health checks."""
from pathlib import Path
from typing import Any
import yaml

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
