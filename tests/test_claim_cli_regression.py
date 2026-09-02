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
