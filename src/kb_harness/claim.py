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

def plan_claim_transition(path: Path, status: str) -> ClaimPlan:
    from kb_ontology_core import plan_transition
    doc = parse_document(str(path), path.read_text(encoding="utf-8"))
    errors = plan_transition(doc.frontmatter.get("status"), status)
    if errors: raise ClaimSpecError(errors[0], "claim.transition.invalid")
    fm = dict(doc.frontmatter); fm["status"] = status
    text = "---\n" + yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).rstrip() + "\n---\n" + doc.body
    return ClaimPlan(((path, text),), path)
