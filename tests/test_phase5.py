import json
from pathlib import Path

from kb_harness.references import reference_health
from kb_harness.cli import main


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
