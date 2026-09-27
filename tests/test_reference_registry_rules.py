"""references.yml のローダと検査規則が validate / health / create で 1 つであることの回帰テスト。

BACKLOG R1 が挙げた 3 件の不整合を対象とする。
- (a) validate は list / str の references.yml で AttributeError → exit 3 になっていた。
- (b) create は type / title / URL 形式しか見ず、validate で弾かれる spec
      （`{type: web, title: x}` のような url 欠落）がそのまま通っていた。
- (c) 重複検出がモジュール大域で、1 エントリ内の入れ子 mapping の重複キー
      （`author:` を 2 回書く等）まで `reference.duplicate.id` と誤報告していた。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from kb_harness.cli import main
from kb_harness.references import ReferenceSpecError, plan_reference_create, reference_health
from kb_harness.validation import validate


def _project(tmp_path: Path, references_text: str) -> Path:
    content = tmp_path / "content"
    content.mkdir()
    (tmp_path / "kb-domain.yml").write_text(
        "domain:\n  content_root: content\n", encoding="utf-8"
    )
    (content / "references.yml").write_text(references_text, encoding="utf-8")
    (content / "vocabulary.yml").write_text(
        "types:\n  Index:\n    directory: null\n    graph: false\n"
        "predicates: {}\ntags: []\n",
        encoding="utf-8",
    )
    (content / "index.md").write_text(
        "---\ntype: Index\ntitle: Fixture\ndescription: Fixture root.\ntags: []\nsources: []\n---\n"
        "# Fixture\n",
        encoding="utf-8",
    )
    return tmp_path


# --- (a) 非 mapping ルート（list / str）でクラッシュしない -----------------


def test_validate_reports_clean_error_for_list_references_root(tmp_path):
    root = _project(tmp_path, "- just\n- a\n- list\n")
    # かつては references.yml が list だと _load_references が dict.items() を
    # 呼んで AttributeError を送出し、CLI 側は internal.error (exit 3) になっていた。
    errors = validate(root / "content")
    assert any("references.yml must be a mapping" in e for e in errors)


def test_validate_cli_does_not_crash_for_str_references_root(tmp_path, capsys):
    root = _project(tmp_path, '"just a string"\n')
    code = main(["validate", "--start", str(root), "--format", "json"])
    # exit 3 (internal.error) ではなく、通常の検証失敗 (exit 1) として報告される。
    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    codes = {d["code"] for d in payload["diagnostics"]}
    assert codes == {"validation.error"}
    assert any("references.yml must be a mapping" in d["message"] for d in payload["diagnostics"])


def test_reference_health_reports_clean_error_for_list_root(tmp_path):
    path = tmp_path / "references.yml"
    path.write_text("- just\n- a\n- list\n", encoding="utf-8")
    result = reference_health(path)
    assert result["ok"] is False
    assert result["diagnostics"][0]["code"] == "reference.root.mapping"


# --- (b) create は validate と同じ規則を見る -------------------------------


def test_reference_create_rejects_what_validate_would_reject(tmp_path):
    root = _project(tmp_path, "{}\n")
    spec = tmp_path / "spec.yml"
    # type: web は url が必須。以前は create を素通りし、直後の validate で
    # 初めて `type 'web' requires 'url'` として弾かれていた。
    spec.write_text("id: no-url\ntype: web\ntitle: x\n", encoding="utf-8")
    with pytest.raises(ReferenceSpecError) as exc:
        plan_reference_create(root / "content" / "references.yml", spec)
    assert exc.value.code == "reference.missing.url"

    # create を通り抜けてしまった場合に validate がどう見るかも、
    # 同じ規則である以上一致して当然だが、ここでは create 側で先に止まることを確認する。


def test_reference_create_cli_rejects_web_without_url(tmp_path, capsys):
    root = _project(tmp_path, "{}\n")
    spec = tmp_path / "spec.yml"
    spec.write_text("id: no-url\ntype: web\ntitle: x\n", encoding="utf-8")
    code = main(
        [
            "reference",
            "create",
            "--from",
            str(spec),
            "--start",
            str(root),
            "--format",
            "json",
        ]
    )
    assert code == 1
    result = json.loads(capsys.readouterr().out)
    assert result["diagnostics"][0]["code"] == "reference.missing.url"
    # references.yml には書き込まれていない。
    assert (root / "content" / "references.yml").read_text(encoding="utf-8") == "{}\n"


def test_reference_create_rejects_book_without_url_or_bibliography(tmp_path):
    root = _project(tmp_path, "{}\n")
    spec = tmp_path / "spec.yml"
    spec.write_text("id: bare\ntype: book\ntitle: x\n", encoding="utf-8")
    with pytest.raises(ReferenceSpecError) as exc:
        plan_reference_create(root / "content" / "references.yml", spec)
    assert exc.value.code == "reference.missing.url_or_bibliography"


# --- (c) 重複検出はルート mapping だけを見る -------------------------------


def test_duplicate_detection_ignores_nested_mapping_duplicates(tmp_path):
    # 1 エントリ内で `author:` を 2 回書いても、ルートの重複ではない。
    path = tmp_path / "references.yml"
    path.write_text(
        "a:\n"
        "  type: book\n"
        "  title: A\n"
        "  author: Alice\n"
        "  author: Bob\n"
        "b:\n"
        "  type: book\n"
        "  title: B\n"
        "  author: Carol\n",
        encoding="utf-8",
    )
    result = reference_health(path)
    codes = [d["code"] for d in result["diagnostics"]]
    assert "reference.duplicate.id" not in codes


def test_duplicate_detection_still_catches_root_level_duplicates(tmp_path):
    path = tmp_path / "references.yml"
    path.write_text(
        "a:\n  type: book\n  title: A\n  author: Alice\n"
        "a:\n  type: web\n  title: A2\n  url: https://example.com\n",
        encoding="utf-8",
    )
    result = reference_health(path)
    codes = [d["code"] for d in result["diagnostics"]]
    assert codes.count("reference.duplicate.id") == 1


def test_validate_ignores_nested_mapping_duplicates(tmp_path):
    root = _project(
        tmp_path,
        "a:\n"
        "  type: book\n"
        "  title: A\n"
        "  author: Alice\n"
        "  author: Bob\n",
    )
    errors = validate(root / "content")
    assert not any("duplicate reference id" in e for e in errors)
