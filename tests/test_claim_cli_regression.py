import json
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
from pathlib import Path

from kb_harness.cli import main


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
    assert code == 0
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
    claim.write_text("---\ntype: Claim\nsubject: /people/a.md\npredicate: taught\nobject: /people/b.md\nstatus: proposed\nconfidence: C\nsources: [x]\n---\n", encoding="utf-8")
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
