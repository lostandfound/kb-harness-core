"""Deterministic actions for Claim documents."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import yaml

from .markdown import parse_document
from .ontology import export_claim

class ClaimSpecError(ValueError):
    def __init__(self, message: str, code: str = "claim.invalid"):
        super().__init__(message); self.code = code

@dataclass(frozen=True)
class ClaimPlan:
    changes: tuple[tuple[Path, str], ...]
    path: Path

def _slug(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return value or "claim"

def load_claim_spec(path: Path) -> dict:
    try: data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as e: raise ClaimSpecError(str(e), "claim.spec.read") from e
    if not isinstance(data, dict): raise ClaimSpecError("Claim spec must be a mapping")
    required = ("subject", "status", "confidence", "sources")
    missing = [k for k in required if not data.get(k)]
    if missing: raise ClaimSpecError("missing required field(s): " + ", ".join(missing))
    relation = any(k in data for k in ("predicate", "object"))
    value = any(k in data for k in ("property", "value"))
    if relation == value or (relation and not data.get("predicate")) or (relation and not data.get("object")) or (value and (not data.get("property") or not data.get("value"))):
        raise ClaimSpecError("claim must use exactly one complete form: predicate/object or property/value")
    return data

def plan_claim_create(project, spec_path: Path) -> ClaimPlan:
    spec = load_claim_spec(spec_path)
    title = spec.get("title") or f"{spec['subject']} {spec.get('predicate', spec.get('property'))}"
    path = project.content_root / "claims" / (_slug(title) + ".md")
    if path.exists(): raise ClaimSpecError(f"claim already exists: {path}", "claim.duplicate")
    fields = {"type": "Claim", "title": title, "description": spec.get("description", ""), "tags": spec.get("tags", []), "timestamp": spec.get("timestamp", "1970-01-01T00:00:00Z"), **spec}
    fields.pop("slug", None)
    body = "\n".join(["---", yaml.safe_dump(fields, allow_unicode=True, sort_keys=False).rstrip(), "---", spec.get("body", ""), ""])
    return ClaimPlan(((path, body),), path)

def inspect_claim(path: Path) -> dict:
    doc = parse_document(str(path), path.read_text(encoding="utf-8"))
    # Graph paths are KB-relative, never filesystem-absolute paths.
    parts = path.resolve().parts
    try:
        start = len(parts) - 1 - list(reversed(parts)).index("claims")
        display_path = "/" + "/".join(parts[start:])
    except ValueError:
        display_path = "/" + path.name
    return export_claim(display_path, doc.frontmatter)

def list_claims(content_root: Path, status: str | None = None) -> list[dict]:
    claims = []
    for path in sorted((content_root / "claims").glob("*.md"), key=lambda p: p.name):
        doc = parse_document(str(path), path.read_text(encoding="utf-8"))
        if status is None or doc.frontmatter.get("status") == status:
            item = {"path": "/claims/" + path.name, **doc.frontmatter}
            # YAML loaders may produce Path/date-like values; CLI JSON is stable.
            item = {key: _json_value(value) for key, value in item.items()}
            claims.append(item)
    return claims

def _json_value(value):
    if isinstance(value, Path): return value.as_posix()
    if isinstance(value, dict): return {str(k): _json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [_json_value(v) for v in value]
    if hasattr(value, "isoformat"): return value.isoformat()
    return value

def validate_claim_file(path: Path) -> list[str]:
    doc = parse_document(str(path), path.read_text(encoding="utf-8"))
    fm = doc.frontmatter
    errors = []
    if fm.get("type") != "Claim": errors.append("type must be Claim")
    for field in ("subject", "status", "confidence", "sources"):
        if not fm.get(field): errors.append("missing field " + field)
    if fm.get("status") not in {"proposed", "accepted", "disputed", "rejected"}: errors.append("unknown status")
    if fm.get("confidence") not in {"A", "B", "C", "D"}: errors.append("unknown confidence")
    return errors

def plan_claim_transition(path: Path, status: str) -> ClaimPlan:
    from kb_ontology_core import plan_transition
    doc = parse_document(str(path), path.read_text(encoding="utf-8"))
    errors = plan_transition(doc.frontmatter.get("status"), status)
    if errors: raise ClaimSpecError(errors[0], "claim.transition.invalid")
    fm = dict(doc.frontmatter); fm["status"] = status
    text = "---\n" + yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).rstrip() + "\n---\n" + doc.body
    return ClaimPlan(((path, text),), path)
