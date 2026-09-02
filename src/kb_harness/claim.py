"""Deterministic actions for Claim documents."""
from __future__ import annotations

from dataclasses import dataclass
import os
import shutil
import tempfile
from pathlib import Path
import re
import yaml

from .markdown import parse_document
from .ontology import Ontology, export_claim, validate_claim
from .graph import plan_graph
from .index import plan_index
from .sync import execute_write_plan, plan_sync, plan_write
from .validation import validate

class ClaimSpecError(ValueError):
    def __init__(self, message: str, code: str = "claim.invalid"):
        super().__init__(message); self.code = code

@dataclass(frozen=True)
class ClaimPlan:
    changes: tuple[tuple[Path, str], ...]
    path: Path
    diff: str = ""

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
    fields = dict(spec)
    fields.update({"type": "Claim", "title": title, "description": spec.get("description") or title, "tags": spec.get("tags", []), "timestamp": spec.get("timestamp", "1970-01-01T00:00:00Z")})
    fields.pop("slug", None)
    body = "\n".join(["---", yaml.safe_dump(fields, allow_unicode=True, sort_keys=False).rstrip(), "---", spec.get("body", ""), ""])
    _validate_proposed_claim(project.content_root, fields)
    return _stage_claim_plan(project, path, body)


def _stage_claim_plan(project, claim_path: Path, claim_text: str) -> ClaimPlan:
    """Validate the complete prospective KB and collect derived artifacts."""
    with tempfile.TemporaryDirectory(prefix="kb-claim-") as tempdir:
        # ``tempfile`` may return macOS's ``/var`` spelling while Path.resolve()
        # (used by the planners below) returns the canonical ``/private/var``
        # spelling.  Keep the staging root canonical from the outset so that
        # relative-path conversion cannot escape the temporary repository.
        stage_root = (Path(tempdir) / "repo").resolve()
        stage_content = stage_root / project.content_root.relative_to(project.repo_root)
        shutil.copytree(project.content_root, stage_content, symlinks=True)
        config = project.repo_root / "kb-domain.yml"
        if config.is_file():
            stage_root.mkdir(parents=True, exist_ok=True)
            shutil.copy2(config, stage_root / "kb-domain.yml")
        graph = project.repo_root / "graph.json"
        if graph.is_file(): shutil.copy2(graph, stage_root / "graph.json")
        evals = project.repo_root / "evals"
        if evals.is_dir(): shutil.copytree(evals, stage_root / "evals", symlinks=True)
        # Callers may provide a path through a macOS ``/var`` symlink while the
        # project itself was resolved to ``/private/var``.  Compare canonical
        # paths for containment/relativization, while retaining the caller's
        # lexical path as the eventual write target in the returned plan.
        try:
            claim_relative = claim_path.resolve().relative_to(project.content_root.resolve())
        except ValueError as error:
            raise ClaimSpecError(
                f"claim path must be inside content root: {claim_path}",
                "claim.path.outside_content",
            ) from error
        staged_claim = stage_content / claim_relative
        staged_claim.parent.mkdir(parents=True, exist_ok=True)
        staged_claim.write_text(claim_text, encoding="utf-8")
        staged_project = type(project)(repo_root=stage_root, content_root=stage_content)
        derived = {**plan_index(stage_content), **plan_graph(stage_content, stage_root / "graph.json")}
        execute_write_plan(plan_write(derived))
        errors = validate(stage_content)
        if errors:
            raise ClaimSpecError("new claim failed full validation: " + "; ".join(errors), "claim.validation")
        if plan_sync(staged_project):
            raise ClaimSpecError("new claim leaves derived artifacts out of sync", "claim.sync")
        changes = {claim_path: claim_text}
        for staged_path in derived:
            real = project.repo_root / os.path.relpath(staged_path, stage_root)
            changes[real] = staged_path.read_text(encoding="utf-8")
        ordered = tuple(sorted(changes.items(), key=lambda item: str(item[0])))
        from .sync import unified_diff
        return ClaimPlan(
            ordered,
            claim_path,
            unified_diff(dict(ordered), display_root=project.repo_root),
        )

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

def validate_claim_file(path: Path, content_root: Path | None = None) -> list[str]:
    doc = parse_document(str(path), path.read_text(encoding="utf-8"))
    fm = doc.frontmatter
    errors = []
    if fm.get("type") != "Claim": errors.append("type must be Claim")
    for field in ("subject", "status", "confidence", "sources"):
        if not fm.get(field): errors.append("missing field " + field)
    if fm.get("status") not in {"proposed", "accepted", "disputed", "rejected"}: errors.append("unknown status")
    if fm.get("confidence") not in {"A", "B", "C", "D"}: errors.append("unknown confidence")
    if errors:
        return errors
    try:
        _validate_proposed_claim(content_root or path.parent.parent, dict(fm), exclude=path)
    except ClaimSpecError as error:
        return [str(error)]
    return []

def plan_claim_transition(path: Path, status: str, project=None) -> ClaimPlan:
    from kb_ontology_core import plan_transition
    doc = parse_document(str(path), path.read_text(encoding="utf-8"))
    errors = plan_transition(doc.frontmatter.get("status"), status)
    if errors: raise ClaimSpecError(errors[0], "claim.transition.invalid")
    fm = dict(doc.frontmatter); fm["status"] = status
    text = "---\n" + yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).rstrip() + "\n---\n" + doc.body
    if project is None:
        from .sync import unified_diff
        return ClaimPlan(((path, text),), path, unified_diff({path: text}))
    return _stage_claim_plan(project, path, text)


def _validate_proposed_claim(content_root: Path, claim: dict, exclude: Path | None = None) -> None:
    """Validate a new Claim against existing entities, edges, and Claims."""
    from .validation import _iter_entity_files, _load_properties, _load_vocabulary

    predicates, _ = _load_vocabulary(content_root)
    ontology = Ontology.from_mapping({"predicates": predicates, "properties": _load_properties(content_root)})
    entities: dict[str, str] = {}
    edges: set[tuple[str, str, str]] = set()
    claims: set[tuple[str, str, str, str]] = set()
    for candidate in _iter_entity_files(content_root):
        if candidate.name == "vocabulary.yml":
            continue
        try:
            fm = parse_document(str(candidate), candidate.read_text(encoding="utf-8")).frontmatter
        except Exception as error:
            raise ClaimSpecError(
                f"existing document cannot be parsed: {candidate}: {error}",
                "claim.validation",
            ) from error
        rel = "/" + str(candidate.relative_to(content_root))
        entities[rel] = str(fm.get("type", ""))
        for relation in fm.get("relations") or []:
            if isinstance(relation, dict) and relation.get("predicate") and relation.get("target"):
                edges.add((rel, relation["predicate"], relation["target"]))
        if fm.get("type") == "Claim" and candidate != exclude:
            kind = "relation" if fm.get("predicate") else "value"
            key = (kind, fm.get("subject"), fm.get("predicate", fm.get("property")), fm.get("object", fm.get("value")))
            claims.add(key)
    kind = "relation" if claim.get("predicate") else "value"
    key = (kind, claim.get("subject"), claim.get("predicate", claim.get("property")), claim.get("object", claim.get("value")))
    if key in claims:
        raise ClaimSpecError("claim duplicates existing Claim", "claim.duplicate")
    errors = validate_claim("/claims/<new>", claim, entities, ontology, edges)
    if errors:
        raise ClaimSpecError("; ".join(errors), "claim.validation")
