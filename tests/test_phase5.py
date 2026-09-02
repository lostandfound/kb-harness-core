import json
from pathlib import Path

from kb_harness.references import reference_health
from kb_harness.cli import main


def _reference_project(tmp_path):
    (tmp_path / "content").mkdir()
    (tmp_path / "kb-domain.yml").write_text("domain:\n  content_root: content\n", encoding="utf-8")
    (tmp_path / "content" / "references.yml").write_text(
        "existing:\n  type: web\n  title: Existing\n", encoding="utf-8"
    )
    return tmp_path


def test_reference_create_from_spec_is_deterministic(tmp_path, capsys):
    root = _reference_project(tmp_path)
    spec = root / "ref.yml"
    spec.write_text("id: new-ref\ntype: book\ntitle: New\nurl: https://example.com\n", encoding="utf-8")
    assert main(["reference", "create", "--from", str(spec), "--start", str(root), "--format", "json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["changed"] == ["references.yml"]
    assert "new-ref:" in (root / "content" / "references.yml").read_text(encoding="utf-8")


def test_reference_create_rejects_duplicate_and_invalid_spec(tmp_path, capsys):
    root = _reference_project(tmp_path)
    spec = root / "ref.yml"
    spec.write_text("id: existing\ntype: book\ntitle: New\n", encoding="utf-8")
    assert main(["reference", "create", "--from", str(spec), "--start", str(root), "--format", "json"]) == 2
    assert json.loads(capsys.readouterr().err)["diagnostics"][0]["code"] == "reference.duplicate.id"
    spec.write_text("id: bad\ntype: book\ntitle: New\nurl: ftp://example.com\n", encoding="utf-8")
    assert main(["reference", "create", "--from", str(spec), "--start", str(root), "--format", "json"]) == 2
    assert json.loads(capsys.readouterr().err)["diagnostics"][0]["code"] == "reference.url.invalid"


def test_reference_health_reports_missing_and_duplicate_ids(tmp_path):
    path = tmp_path / "references.yml"
    path.write_text("""a:\n  type: book\n  title: A\na:\n  type: web\n  url: https://example.com\nc:\n  type: book\n""", encoding="utf-8")
    result = reference_health(path)
    codes = {item["code"] for item in result["diagnostics"]}
    assert "reference.missing.url_or_bibliography" in codes
    assert result["ok"] is False


def test_reference_health_is_deterministic_and_accepts_bibliography(tmp_path):
    path = tmp_path / "references.yml"
    path.write_text("""b:\n  type: book\n  title: B\n  author: Author\n  year: 2020\n""", encoding="utf-8")
    assert reference_health(path)["ok"] is True


def test_eval_commands_report_missing_assets(tmp_path, capsys):
    (tmp_path / "content").mkdir()
    (tmp_path / "content" / "references.yml").write_text("{}", encoding="utf-8")
    (tmp_path / "kb-domain.yml").write_text("domain:\n  content_root: content\n", encoding="utf-8")
    assert main(["eval", "summary", "--start", str(tmp_path), "--format", "json"]) == 1
    output = json.loads(capsys.readouterr().err)
    assert output["diagnostics"][0]["code"] == "eval.assets.missing"


def test_eval_summary_discovers_repo_evals(tmp_path, capsys):
    (tmp_path / "content").mkdir()
    (tmp_path / "kb-domain.yml").write_text("domain:\n  content_root: content\n", encoding="utf-8")
    (tmp_path / "evals").mkdir()
    (tmp_path / "evals" / "rag-eval.yml").write_text("entries: []\n", encoding="utf-8")
    assert main(["eval", "summary", "--start", str(tmp_path), "--format", "json"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["assets"] == ["evals/rag-eval.yml"]

def test_eval_summary_reports_verdicts_and_gaps(tmp_path, capsys):
    (tmp_path / "content").mkdir()
    (tmp_path / "kb-domain.yml").write_text("domain:\n content_root: content\n", encoding="utf-8")
    (tmp_path / "evals").mkdir()
    (tmp_path / "evals" / "rag-eval.yml").write_text(
        "entries:\n"
        "  - id: ok\n    kind: fact\n    history:\n      - {date: '2026-08-01', verdict: OK}\n"
        "  - id: open\n    kind: fact\n    gap: missing-text\n    history:\n      - {date: '2026-08-01', verdict: 回答不能}\n",
        encoding="utf-8",
    )
    assert main(["eval", "summary", "--start", str(tmp_path), "--format", "json"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["summary"]["evaluated"] == 2
    assert output["summary"]["by_verdict"]["OK"] == 1
    assert output["open_gaps"][0]["id"] == "open"

def test_eval_summary_accepts_top_level_entry_list(tmp_path, capsys):
    (tmp_path / "content").mkdir()
    (tmp_path / "kb-domain.yml").write_text("domain:\n content_root: content\n", encoding="utf-8")
    (tmp_path / "evals").mkdir()
    (tmp_path / "evals" / "rag-eval.yml").write_text(
        "- id: q1\n  kind: fact\n  history:\n    - {date: '2026-09-01', verdict: OK}\n",
        encoding="utf-8",
    )
    assert main(["eval", "summary", "--start", str(tmp_path), "--format", "json"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["summary"]["evaluated"] == 1
    assert output["summary"]["by_verdict"] == {"OK": 1}
