"""2026-09-27 レビューの High 指摘に対する回帰テスト。

- timestamp / title / description を YAML が型解決した値でも検査する
- kb eval smoke / summary が本体ライブラリ（kb_harness.evaluation）で動く
- Claim の遷移がオントロジーコアの解決を ontology.load_ontology_core に委ねる
- 互換スクリプトの --root 既定値が遅延評価され、cwd に依存しない
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from kb_harness.cli import main
from kb_harness.diagnostics import HarnessError

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"

ENTITY = (
    "---\ntype: Person\ntitle: 太郎\ndescription: {description}\ntags: [x]\n"
    "sources: [https://example.test]\ntimestamp: {timestamp}\n---\n## 概要\n\n本文\n"
)


def _kb(root: Path, *argv: str) -> tuple[int, dict]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main([*argv, "--start", str(root), "--format", "json"])
    return code, json.loads(out.getvalue() or err.getvalue())


def _project(tmp_path: Path, *, timestamp: str = "2024-01-01T00:00:00Z", description: str = "説明") -> Path:
    (tmp_path / "kb-domain.yml").write_text("domain:\n  content_root: content\n", encoding="utf-8")
    content = tmp_path / "content"
    (content / "people").mkdir(parents=True)
    (content / "vocabulary.yml").write_text("types:\n  Person:\n    directory: people\npredicates: {}\ntags: [x]\n", encoding="utf-8")
    index = "---\ntype: Index\ntitle: {t}\ndescription: d\ntags: []\ntimestamp: 2024-01-01T00:00:00Z\n---\n{body}\n"
    (content / "index.md").write_text(index.format(t="index", body="- [Person](people/index.md)"), encoding="utf-8")
    (content / "people" / "index.md").write_text(index.format(t="people", body="- [太郎](taro.md)"), encoding="utf-8")
    (content / "people" / "taro.md").write_text(ENTITY.format(timestamp=timestamp, description=description), encoding="utf-8")
    return tmp_path


def _messages(result: dict) -> list[str]:
    return [d["message"] for d in result["diagnostics"]]


# --- H1 timestamp -------------------------------------------------------------


def test_unquoted_canonical_timestamp_passes(tmp_path: Path):
    code, _ = _kb(_project(tmp_path), "validate")
    assert code == 0


@pytest.mark.parametrize("timestamp", ["2024-01-01 09:00:00", "2024-01-01 00:00:00Z", "2024-01-01T00:00:00+00:00", "2024-01-01T00:00:00+09:00", "2024-01-01T00:00:00.5Z", "'2024-01-01'"])
def test_unquoted_non_utc_or_malformed_timestamp_is_rejected(tmp_path: Path, timestamp: str):
    code, result = _kb(_project(tmp_path, timestamp=timestamp), "validate")
    assert code == 1
    assert any("timestamp" in m for m in _messages(result)), _messages(result)


@pytest.mark.parametrize("timestamp, expected_code", [("2024-01-01T00:00:00Z", 0), ("2024-01-01T00:00:00+00:00", 1)])
def test_merged_timestamp_is_checked_without_internal_error(tmp_path: Path, timestamp: str, expected_code: int):
    root = _project(tmp_path)
    entity = root / "content" / "people" / "taro.md"
    text = entity.read_text(encoding="utf-8")
    entity.write_text(text.replace("timestamp: 2024-01-01T00:00:00Z", f"defaults: &defaults\n  timestamp: {timestamp}\n<<: *defaults"), encoding="utf-8")
    code, result = _kb(root, "validate")
    assert code == expected_code, _messages(result)
    assert not any(d["code"] == "internal.error" for d in result["diagnostics"])


# --- H2 title / description -----------------------------------------------------


def test_non_string_description_is_an_error_and_sync_still_works(tmp_path: Path):
    root = _project(tmp_path, description="2020-01-01")
    code, result = _kb(root, "validate")
    assert code == 1
    assert any("'description' は文字列" in m for m in _messages(result)), _messages(result)
    code, _ = _kb(root, "sync")
    assert code == 0, "graph.json の生成は落ちない（検証が止める）"
    node = json.loads((root / "graph.json").read_text(encoding="utf-8"))["nodes"][0]
    assert node["description"] == "2020-01-01"


# --- H3 kb eval ----------------------------------------------------------------


def _eval_project(tmp_path: Path, entries: str) -> Path:
    root = _project(tmp_path)
    (root / "evals").mkdir()
    (root / "evals" / "rag-eval.yml").write_text(entries, encoding="utf-8")
    return root


def test_validate_accepts_entries_mapping(tmp_path: Path):
    root = _eval_project(
        tmp_path,
        "entries:\n"
        "  - id: example\n"
        "    kind: fact\n"
        "    query: q\n"
        "    expected: a\n"
        "    evidence: [/people/taro.md]\n"
        "    history: [{date: '2026-09-01', verdict: OK}]\n",
    )
    code, result = _kb(root, "validate")
    assert code == 0, _messages(result)


def test_eval_smoke_reports_miss_and_hit(tmp_path: Path):
    root = _eval_project(
        tmp_path,
        "- id: hit\n  kind: fact\n  query: 太郎の本文\n  expected: x\n  evidence: [/people/taro.md]\n"
        "  history: [{date: '2026-09-01', verdict: OK}]\n"
        "- id: miss\n  kind: fact\n  query: 全く無関係な語句 zzz\n  expected: x\n  evidence: [/people/nobody.md]\n"
        "  history: [{date: '2026-09-01', verdict: OK}]\n"
        "- id: planned\n  kind: fact\n  query: q\n  expected: x\n  evidence: [/people/nobody.md]\n  history: []\n",
    )
    code, result = _kb(root, "eval", "smoke", "--limit", "3")
    assert code == 1
    assert result["evaluated"] == 2 and result["limit"] == 3
    assert [f["id"] for f in result["failures"]] == ["miss"]
    assert result["diagnostics"][0]["code"] == "eval.smoke.miss"


def test_eval_smoke_passes_when_every_evidence_is_retrieved(tmp_path: Path):
    root = _eval_project(
        tmp_path,
        "- id: hit\n  kind: fact\n  query: 太郎の本文\n  expected: x\n  evidence: [/people/taro.md]\n"
        "  history: [{date: '2026-09-01', verdict: OK}]\n",
    )
    code, result = _kb(root, "eval", "smoke")
    assert code == 0 and result["ok"] is True and result["failures"] == []


def test_eval_summary_detects_regression(tmp_path: Path):
    root = _eval_project(
        tmp_path,
        "- id: q1\n  kind: fact\n  query: q\n  expected: x\n  evidence: [/people/taro.md]\n"
        "  history:\n    - {date: '2026-08-01', verdict: OK}\n    - {date: '2026-09-01', verdict: 回答不能}\n",
    )
    code, result = _kb(root, "eval", "summary")
    assert code == 1
    assert result["regressions"][0]["id"] == "q1"
    assert result["diagnostics"][0]["code"] == "eval.regression"
    assert result["summary"]["by_verdict"] == {"回答不能": 1}


def test_eval_ignores_unrelated_files_in_evals_dir(tmp_path: Path):
    root = _eval_project(tmp_path, "- id: q1\n  kind: fact\n  history: [{date: '2026-09-01', verdict: OK}]\n")
    (root / "evals" / "README.md").write_text("# memo\n", encoding="utf-8")
    code, result = _kb(root, "eval", "summary")
    assert code == 0 and result["assets"] == ["evals/README.md", "evals/rag-eval.yml"]


def test_compat_scripts_share_the_library(tmp_path: Path):
    sys.path.insert(0, str(SCRIPTS))
    try:
        import eval_summary
        import rag_smoke
        from kb_harness import evaluation
    finally:
        sys.path.remove(str(SCRIPTS))
    assert rag_smoke.evaluate is evaluation.evaluate
    assert eval_summary.find_regressions is evaluation.find_regressions


# --- H4 claim transition -------------------------------------------------------


def test_claim_transition_resolves_core_through_ontology_loader(monkeypatch, tmp_path: Path):
    from kb_harness import claim, ontology

    monkeypatch.setitem(sys.modules, "kb_ontology_core", None)
    monkeypatch.setattr(ontology, "_ontology_core_module", None)
    path = tmp_path / "c.md"
    path.write_text("---\ntype: Claim\nstatus: proposed\n---\n", encoding="utf-8")
    with pytest.raises(HarnessError) as exc:
        claim.plan_claim_transition(path, "accepted")
    assert exc.value.diagnostic.code == "ontology.core.missing"


# --- H5 script root defaults ---------------------------------------------------


@pytest.mark.parametrize("name", ["new_entity.py", "validate.py", "rag_smoke.py", "eval_summary.py"])
def test_scripts_help_works_from_a_directory_without_kb(tmp_path: Path, name: str):
    result = subprocess.run([sys.executable, str(SCRIPTS / name), "--help"], capture_output=True, text=True, cwd=tmp_path)
    assert result.returncode == 0, result.stderr


def test_kb_config_returns_absolute_root_from_cwd(tmp_path: Path):
    root = _project(tmp_path)
    code = (
        "import sys; sys.path.insert(0, %r)\n"
        "from kb_config import default_content_root\n"
        "print(default_content_root())\n" % str(SCRIPTS)
    )
    sub = root / "content" / "people"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=sub)
    assert result.returncode == 0, result.stderr
    assert Path(result.stdout.strip()) == (root / "content").resolve()


def test_rag_smoke_script_from_subdirectory_reads_the_configured_root(tmp_path: Path):
    root = _eval_project(
        tmp_path,
        "- id: hit\n  kind: fact\n  query: 太郎の本文\n  expected: x\n  evidence: [/people/taro.md]\n"
        "  history: [{date: '2026-09-01', verdict: OK}]\n",
    )
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "rag_smoke.py"), "--eval-file", str(root / "evals" / "rag-eval.yml")],
        capture_output=True, text=True, cwd=root / "content" / "people",
    )
    assert result.returncode == 0, result.stdout + result.stderr
