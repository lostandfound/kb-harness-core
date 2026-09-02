import json
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
from pathlib import Path

from kb_harness.cli import _parser, main


def test_claim_parser_preserves_command_surface_and_options():
    # Given the public claim subcommands and their documented options
    parser = _parser()

    # When each command is parsed with its supported arguments
    parsed = [
        parser.parse_args(["claim", "create", "--from", "spec.yml", "--dry-run"]),
        parser.parse_args(["claim", "inspect", "claim.md", "--format", "json"]),
        parser.parse_args(["claim", "list", "--status", "accepted"]),
        parser.parse_args(["claim", "validate", "claim.md"]),
        parser.parse_args(["claim", "transition", "claim.md", "--status", "accepted"]),
    ]

    # Then argparse exposes the same command names and destination attributes
    assert [args.claim_command for args in parsed] == [
        "create", "inspect", "list", "validate", "transition"
    ]
    assert parsed[0].spec == "spec.yml" and parsed[0].dry_run is True
    assert parsed[1].format == "json" and parsed[2].status == "accepted"
    assert parsed[4].legacy_status == "accepted"


def test_claim_inspect_accepts_start_and_emits_json(tmp_path: Path):
    content = tmp_path / "knowledge"
    claims = content / "claims"
    claims.mkdir(parents=True)
    (tmp_path / "kb-domain.yml").write_text("domain:\n  content_root: knowledge\n", encoding="utf-8")
    path = claims / "example.md"
    path.write_text("---\ntype: Claim\ntitle: Example\nsubject: /people/a.md\npredicate: taught\nobject: /people/b.md\nstatus: proposed\nconfidence: C\nsources: [Test]\n---\n", encoding="utf-8")
    output = StringIO()
    with redirect_stdout(output):
        code = main(["claim", "inspect", str(path), "--start", str(tmp_path), "--format", "json"])
    assert code == 0, output.getvalue()
    assert json.loads(output.getvalue())["status"] == "proposed"
    assert json.loads(output.getvalue())["path"] == "/claims/example.md"

def test_claim_inspect_missing_path_is_diagnostic(tmp_path: Path):
    (tmp_path / "kb-domain.yml").write_text("domain:\n  content_root: knowledge\n", encoding="utf-8")
    output = StringIO()
    with redirect_stderr(output):
        code = main(["claim", "inspect", "missing.md", "--start", str(tmp_path), "--format", "json"])
    assert code == 2
    assert json.loads(output.getvalue())["diagnostics"][0]["code"] == "claim.path.not_found"

def test_claim_transition_uses_to_option(tmp_path: Path):
    (tmp_path / "kb-domain.yml").write_text("domain:\n content_root: knowledge\n", encoding="utf-8")
    claim = tmp_path / "knowledge" / "claims" / "example.md"
    claim.parent.mkdir(parents=True)
    (tmp_path / "knowledge" / "people").mkdir()
    (tmp_path / "knowledge" / "vocabulary.yml").write_text("types:\n  Person:\n    directory: people\n  Claim:\n    directory: claims\n    graph: false\npredicates:\n  taught:\n    domain: [Person]\n    range: [Person]\n", encoding="utf-8")
    for name in ("a", "b"):
        (tmp_path / "knowledge" / "people" / f"{name}.md").write_text("---\ntype: Person\ntitle: Person\ndescription: Test\ntags: []\ntimestamp: 2026-01-01T00:00:00Z\nsources: [x]\n---\n", encoding="utf-8")
    claim.write_text("---\ntype: Claim\ntitle: Example\ndescription: Test\ntags: []\ntimestamp: 2026-01-01T00:00:00Z\nsubject: /people/a.md\npredicate: taught\nobject: /people/b.md\nstatus: proposed\nconfidence: C\nsources: [x]\n---\n", encoding="utf-8")
    output = StringIO()
    with redirect_stdout(output):
        code = main(["claim", "transition", "claims/example.md", "--to", "accepted", "--start", str(tmp_path), "--format", "json"])
    assert code == 0
    assert json.loads(output.getvalue())["ok"] is True
    assert "status: accepted" in claim.read_text(encoding="utf-8")

def test_claim_list_is_sorted_and_filters_status(tmp_path: Path):
    (tmp_path / "kb-domain.yml").write_text("domain:\n content_root: knowledge\n", encoding="utf-8")
    claims = tmp_path / "knowledge" / "claims"
    claims.mkdir(parents=True)
    for name, status in (("zeta", "proposed"), ("alpha", "accepted")):
        (claims / f"{name}.md").write_text(f"---\ntype: Claim\ntitle: {name}\nstatus: {status}\n---\n", encoding="utf-8")
    output = StringIO()
    with redirect_stdout(output):
        code = main(["claim", "list", "--status", "accepted", "--start", str(tmp_path), "--format", "json"])
    result = json.loads(output.getvalue())
    assert code == 0 and [item["path"] for item in result["claims"]] == ["/claims/alpha.md"]

def test_claim_validate_reports_invalid_claim(tmp_path: Path):
    (tmp_path / "kb-domain.yml").write_text("domain:\n content_root: knowledge\n", encoding="utf-8")
    claim = tmp_path / "knowledge" / "claims" / "bad.md"
    claim.parent.mkdir(parents=True)
    claim.write_text("---\ntype: Claim\nsubject: /people/a.md\nstatus: nope\n---\n", encoding="utf-8")
    output = StringIO()
    with redirect_stderr(output):
        code = main(["claim", "validate", "claims/bad.md", "--start", str(tmp_path), "--format", "json"])
    assert code == 1

def test_claim_validate_uses_ontology_context(tmp_path: Path):
    (tmp_path / "kb-domain.yml").write_text("domain:\n content_root: knowledge\n", encoding="utf-8")
    content = tmp_path / "knowledge"
    (content / "people").mkdir(parents=True)
    (content / "claims").mkdir()
    (content / "vocabulary.yml").write_text("types:\n  Person:\n    directory: people\npredicates:\n  taught:\n    domain: [Person]\n    range: [Person]\n", encoding="utf-8")
    for n in ("a", "b"):
        (content / "people" / f"{n}.md").write_text("---\ntype: Person\n---\n", encoding="utf-8")
    claim = content / "claims" / "bad.md"
    claim.write_text("---\ntype: Claim\nsubject: /people/a.md\npredicate: unknown\nobject: /people/b.md\nstatus: proposed\nconfidence: C\nsources: [x]\n---\n", encoding="utf-8")
    output = StringIO()
    with redirect_stderr(output):
        code = main(["claim", "validate", "claims/bad.md", "--start", str(tmp_path), "--format", "json"])
    result = json.loads(output.getvalue())
    assert code == 1 and result["diagnostics"][0]["code"] == "claim.validation"

def test_claim_transition_validates_and_is_atomic(tmp_path: Path):
    (tmp_path / "kb-domain.yml").write_text("domain:\n content_root: knowledge\n", encoding="utf-8")
    claim = tmp_path / "knowledge" / "claims" / "bad.md"
    claim.parent.mkdir(parents=True)
    (tmp_path / "knowledge" / "people").mkdir()
    (tmp_path / "knowledge" / "vocabulary.yml").write_text("types:\n  Person:\n    directory: people\n  Claim:\n    directory: claims\n    graph: false\npredicates:\n  taught:\n    domain: [Person]\n    range: [Person]\n", encoding="utf-8")
    (tmp_path / "knowledge" / "people" / "b.md").write_text("---\ntype: Person\ntitle: Person\ndescription: Test\ntags: []\ntimestamp: 2026-01-01T00:00:00Z\nsources: [x]\n---\n", encoding="utf-8")
    original = "---\ntype: Claim\nsubject: /people/missing.md\npredicate: taught\nobject: /people/b.md\nstatus: proposed\nconfidence: C\nsources: [x]\n---\n"
    claim.write_text(original, encoding="utf-8")
    output = StringIO()
    with redirect_stderr(output):
        code = main(["claim", "transition", "claims/bad.md", "--to", "accepted", "--start", str(tmp_path), "--format", "json"])
    result = json.loads(output.getvalue())
    assert code == 1
    assert result["diagnostics"][0]["code"] == "claim.validation"
    assert claim.read_text(encoding="utf-8") == original


def test_claim_transition_rejects_path_outside_content_root_without_changes(tmp_path: Path):
    (tmp_path / "kb-domain.yml").write_text("domain:\n  content_root: knowledge\n", encoding="utf-8")
    (tmp_path / "knowledge").mkdir()
    outside = tmp_path / "outside.md"
    original = "---\ntype: Claim\nstatus: proposed\nconfidence: C\nsources: [x]\n---\n"
    outside.write_text(original, encoding="utf-8")
    before = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    output = StringIO()
    with redirect_stderr(output):
        code = main(
            [
                "claim",
                "transition",
                "../outside.md",
                "--to",
                "accepted",
                "--start",
                str(tmp_path),
                "--format",
                "json",
            ]
        )

    result = json.loads(output.getvalue())
    after = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert code == 2
    assert result["diagnostics"][0]["code"] == "claim.path.outside_content"
    assert after == before
