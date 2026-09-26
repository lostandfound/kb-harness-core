import pytest
from kb_harness import ontology
from kb_harness.ontology import ontology_core_available

pytestmark = pytest.mark.skipif(not ontology_core_available(), reason="kb-ontology-core が入っていない（Claim を使うテスト）")


def test_ontology_adapter_translates_by_structured_code(monkeypatch):
    diagnostic = ontology.Diagnostic(
        "claim.predicate.unknown",
        "an implementation-specific message",
        field="predicate",
        context={"value": "unknown"},
    )
    monkeypatch.setattr(
        ontology.load_ontology_core(),
        "validate_claim",
        lambda *_args: [diagnostic],
    )

    errors = ontology.validate_claim(
        "/claims/example.md",
        {"predicate": "unknown"},
        {},
        object(),
        (),
    )

    assert errors == ["ERROR /claims/example.md: Claim unknown predicate 'unknown'"]
