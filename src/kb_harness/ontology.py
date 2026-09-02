"""Bridge from the Markdown harness to the ontology domain package."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable, Mapping


def _import_core():
    try:
        import kb_ontology_core
        return kb_ontology_core
    except ModuleNotFoundError as error:
        if error.name != "kb_ontology_core":
            raise

    sibling_src = Path(__file__).resolve().parents[3] / "kb-ontology-core" / "src"
    if sibling_src.is_dir():
        sys.path.insert(0, str(sibling_src))
        import kb_ontology_core
        return kb_ontology_core

    raise ModuleNotFoundError(
        "kb-ontology-core is required; install it or place it beside kb-harness-core"
    )


_core = _import_core()
Diagnostic = _core.Diagnostic
Ontology = _core.Ontology
export_claim = _core.export_claim


def _translate_diagnostic(path: str, diagnostic: Diagnostic) -> str:
    """Translate a core diagnostic without inspecting its human text.

    The harness keeps its historical text return value for compatibility.  All
    branching is keyed by the core's stable code; ``field`` and ``context``
    provide the values needed to render the old Japanese/English messages.
    """
    context = diagnostic.context or {}
    field = diagnostic.field
    value = context.get("value")
    if diagnostic.code == "claim.field.missing":
        message = f"Claim missing required field '{field}'"
    elif diagnostic.code == "claim.sources.empty":
        message = "Claim sources must contain at least one entry"
    elif diagnostic.code == "claim.status.unknown":
        if value is None:
            message = f"Claim {diagnostic}"
        else:
            message = f"Claim status '{value}' は許容値でない"
    elif diagnostic.code == "claim.confidence.unknown":
        message = f"Claim confidence '{value}' は A/B/C/D のいずれか"
    elif diagnostic.code in {"claim.subject.not_found", "claim.object.not_found"}:
        message = f"Claim {field} '{value}' does not exist"
    elif diagnostic.code in {"claim.predicate.unknown", "claim.property.unknown"}:
        message = f"Claim unknown {field} '{value}'"
    elif diagnostic.code == "claim.form.invalid":
        message = "Claim 形式は predicate/object または property/value のどちらか一方を完全に指定する"
    elif diagnostic.code in {
        "claim.predicate.domain_violation",
        "claim.predicate.range_violation",
        "claim.property.domain_violation",
    }:
        message = f"Claim {diagnostic}（型制約違反）"
    elif diagnostic.code == "claim.duplicate_relation":
        message = "relation と Claim の三つ組が重複"
    elif diagnostic.code == "claim.value.invalid_format":
        message = f"Claim {diagnostic}（year-expression の形式でない）"
    elif diagnostic.code == "claim.value_type.unknown":
        message = f"Claim {diagnostic}"
    else:
        # Future core diagnostics remain visible without making the adapter
        # depend on their wording.
        message = f"Claim {diagnostic}"
    return f"ERROR {path}: {message}"


def validate_claim(
    path: str,
    claim: Mapping[str, object],
    entities: Mapping[str, str],
    ontology,
    relation_edges: Iterable[tuple[str, str, str]],
) -> list[str]:
    """Validate through kb-ontology-core while preserving harness diagnostics."""
    return [_translate_diagnostic(path, diagnostic) for diagnostic in _core.validate_claim(claim, entities, ontology, relation_edges)]
