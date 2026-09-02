from kb_harness import ontology


def test_ontology_adapter_translates_by_structured_code(monkeypatch):
    diagnostic = ontology.Diagnostic(
        "claim.predicate.unknown",
        "an implementation-specific message",
        field="predicate",
        context={"value": "unknown"},
    )
    monkeypatch.setattr(
        ontology._core,
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
