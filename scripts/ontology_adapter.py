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

    sibling_src = Path(__file__).resolve().parents[2] / "kb-ontology-core" / "src"
    if sibling_src.is_dir():
        sys.path.insert(0, str(sibling_src))
        import kb_ontology_core
        return kb_ontology_core

    raise ModuleNotFoundError(
        "kb-ontology-core is required; install it or place it beside kb-harness-core"
    )


_core = _import_core()
Ontology = _core.Ontology
export_claim = _core.export_claim


def validate_claim(
    path: str,
    claim: Mapping[str, object],
    entities: Mapping[str, str],
    ontology,
    relation_edges: Iterable[tuple[str, str, str]],
) -> list[str]:
    """Validate through kb-ontology-core while preserving harness diagnostics."""
    translated = []
    for error in _core.validate_claim(claim, entities, ontology, relation_edges):
        if error.startswith("missing field"):
            message = f"Claim missing required {error[8:]}"
        elif error.startswith("unknown status"):
            message = f"Claim status {error[14:]} は許容値でない"
        elif error.startswith("unknown confidence"):
            message = f"Claim confidence {error[18:]} は A/B/C/D のいずれか"
        elif "must use exactly one complete form" in error:
            message = "Claim 形式は predicate/object または property/value のどちらか一方を完全に指定する"
        elif error.startswith("subject ") or error.startswith("object "):
            message = f"Claim {error}"
        elif error.startswith("unknown predicate") or error.startswith("unknown property"):
            message = f"Claim {error}"
        elif "domain violation" in error or "range violation" in error:
            message = f"Claim {error}（型制約違反）"
        elif error == "claim duplicates relation edge":
            message = "relation と Claim の三つ組が重複"
        elif "year-expression" in error:
            message = f"Claim {error}（year-expression の形式でない）"
        else:
            message = f"Claim {error}"
        translated.append(f"ERROR {path}: {message}")
    return translated
