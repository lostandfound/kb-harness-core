"""Compatibility exports for the packaged ontology bridge."""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from kb_harness.ontology import Ontology, export_claim, validate_claim
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from kb_harness.ontology import Ontology, export_claim, validate_claim

__all__ = ["Ontology", "export_claim", "validate_claim"]
