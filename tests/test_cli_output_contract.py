"""`kb` CLI の出力契約（R2, docs/cli.md 共通仕様）の回帰テスト。

- `--format json` は成功・失敗を問わず常に stdout に出る。
- `--dry-run` の text 出力は書き込み済みを装わない。
"""

import io
import json
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from kb_harness.cli import main


def _run(*args):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(list(args))
    return code, out.getvalue(), err.getvalue()


@pytest.mark.parametrize(
    "args,expect_code",
    [
        (("okf", "validate", "__MISSING__/bundle", "--format", "json"), 2),
        (("entity", "create", "--from", "__MISSING__/spec.yml", "--start", "__ROOT__", "--format", "json"), 2),
        (("reference", "create", "--from", "__MISSING__/spec.yml", "--start", "__ROOT__", "--format", "json"), 2),
        (("view", "resolve", "no-such-view", "--start", "__ROOT__", "--format", "json"), 1),
    ],
)
def test_json_failures_always_go_to_stdout(tmp_path, args, expect_code):
    root = tmp_path
    content = root / "knowledge"
    content.mkdir()
    (root / "kb-domain.yml").write_text(
        "domain:\n  content_root: knowledge\nviews:\n  root: views\n", encoding="utf-8"
    )
    (content / "vocabulary.yml").write_text(
        "types:\n  Note:\n    directory: notes\npredicates: {}\ntags: []\n", encoding="utf-8"
    )
    (content / "references.yml").write_text("{}\n", encoding="utf-8")
    (root / "views").mkdir()

    resolved = tuple(
        value.replace("__MISSING__", str(root / "does-not-exist")).replace("__ROOT__", str(root))
        for value in args
    )
    code, out, err = _run(*resolved)
    assert code == expect_code, (out, err)
    assert err == "", "json output must not leak to stderr"
    payload = json.loads(out)
    assert payload["ok"] is False


def test_json_failure_for_project_show_goes_to_stdout(tmp_path):
    # A start directory with no `kb-domain.yml` anywhere above it.
    isolated = tmp_path / "isolated"
    isolated.mkdir()
    code, out, err = _run("project", "show", "--start", str(isolated), "--format", "json")
    assert code == 2, (out, err)
    assert err == "", "json output must not leak to stderr"
    payload = json.loads(out)
    assert payload["ok"] is False


def test_reference_create_content_error_exits_one_like_entity_create(tmp_path):
    # 重複 ID は「内容の問題」であり、entity create の重複（exit 1）と揃える。
    root = tmp_path
    content = root / "knowledge"
    content.mkdir()
    (root / "kb-domain.yml").write_text("domain:\n  content_root: knowledge\n", encoding="utf-8")
    (content / "vocabulary.yml").write_text(
        "types:\n  Concept:\n    directory: concepts\npredicates: {}\ntags: []\n", encoding="utf-8"
    )
    (content / "references.yml").write_text("dup:\n  type: web\n  title: Existing\n  url: https://example.test\n", encoding="utf-8")
    spec = root / "ref.yml"
    spec.write_text("id: dup\ntype: book\ntitle: New\n", encoding="utf-8")

    code, out, err = _run("reference", "create", "--from", str(spec), "--start", str(root), "--format", "json")
    assert code == 1
    assert err == ""
    assert json.loads(out)["diagnostics"][0]["code"] == "reference.duplicate.id"


def test_okf_validate_accepts_start_option(tmp_path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "note.md").write_text("---\ntype: Note\n---\n", encoding="utf-8")
    code, out, err = _run("okf", "validate", "bundle", "--start", str(tmp_path), "--format", "json")
    assert code == 0, (out, err)
    assert json.loads(out)["ok"] is True
