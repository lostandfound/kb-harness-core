from __future__ import annotations

import json
from pathlib import Path

import yaml

from kb_harness.cli import main
from kb_harness.references import plan_reference_create


def _spec(tmp_path: Path, text: str = "id: new-ref\ntype: book\ntitle: New\n") -> Path:
    path = tmp_path / "reference.yml"
    path.write_text(text, encoding="utf-8")
    return path


def test_reference_create_appends_without_reserializing_existing_yaml(tmp_path: Path):
    references = tmp_path / "references.yml"
    original = (
        "# Keep this comment\n"
        '"z-ref":\n'
        '  type: "web"\n'
        '  title: "Quoted title"\n'
        "\n"
    )
    references.write_text(original, encoding="utf-8")

    plan = plan_reference_create(references, _spec(tmp_path))
    expected_entry = yaml.safe_dump(
        {"new-ref": {"type": "book", "title": "New"}},
        allow_unicode=True,
        sort_keys=False,
    )

    assert plan.changes[references] == original + expected_entry
    assert plan.changes[references].startswith(original)
    assert yaml.safe_load(plan.changes[references])["new-ref"] == {
        "type": "book",
        "title": "New",
    }


def test_reference_create_adds_only_missing_eof_newline(tmp_path: Path):
    references = tmp_path / "references.yml"
    original = "existing:\n  type: web\n  title: Existing"
    references.write_text(original, encoding="utf-8")

    plan = plan_reference_create(references, _spec(tmp_path))

    assert plan.changes[references].startswith(original + "\n")
    assert plan.changes[references].count("existing:") == 1
    assert "existing:  new-ref:" not in plan.changes[references]


def test_reference_create_replaces_empty_mapping(tmp_path: Path):
    references = tmp_path / "references.yml"
    references.write_text("{}\n", encoding="utf-8")

    plan = plan_reference_create(references, _spec(tmp_path))
    output = plan.changes[references]

    assert output == yaml.safe_dump(
        {"new-ref": {"type": "book", "title": "New"}},
        allow_unicode=True,
        sort_keys=False,
    )
    assert yaml.safe_load(output)["new-ref"] == {"type": "book", "title": "New"}


def test_reference_create_supports_missing_registry(tmp_path: Path):
    references = tmp_path / "references.yml"

    plan = plan_reference_create(references, _spec(tmp_path))
    output = plan.changes[references]

    assert yaml.safe_load(output)["new-ref"] == {"type": "book", "title": "New"}
    assert output.startswith("new-ref:\n")


def test_reference_create_empty_mapping_dry_run_reports_replacement(
    tmp_path: Path, capsys
):
    content = tmp_path / "content"
    content.mkdir()
    (tmp_path / "kb-domain.yml").write_text(
        "domain:\n  content_root: content\n", encoding="utf-8"
    )
    references = content / "references.yml"
    original = "{}\n"
    references.write_text(original, encoding="utf-8")
    spec = _spec(tmp_path)

    assert (
        main(
            [
                "reference",
                "create",
                "--from",
                str(spec),
                "--start",
                str(tmp_path),
                "--format",
                "json",
                "--dry-run",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)

    assert result["dry_run"] is True
    assert "-{}" in result["diff"]
    assert "+new-ref:" in result["diff"]
    assert references.read_text(encoding="utf-8") == original


def test_reference_create_preserves_crlf_and_uses_it_for_new_entry(tmp_path: Path):
    references = tmp_path / "references.yml"
    original = (
        b'# Keep this comment\r\n'
        b'"existing":\r\n'
        b'  type: "web"\r\n'
        b'  title: Existing\r\n'
    )
    references.write_bytes(original)

    plan = plan_reference_create(references, _spec(tmp_path))
    output = plan.changes[references].encode("utf-8")
    bare_lf = output.replace(b"\r\n", b"")

    assert output.startswith(original)
    assert b"\n" not in bare_lf
    assert yaml.safe_load(output.decode("utf-8"))["new-ref"] == {
        "type": "book",
        "title": "New",
    }
    assert "+new-ref:" in plan.diff


def test_reference_create_crlf_dry_run_reports_diff_and_keeps_file(
    tmp_path: Path, capsys
):
    content = tmp_path / "content"
    content.mkdir()
    (tmp_path / "kb-domain.yml").write_text(
        "domain:\r\n  content_root: content\r\n", encoding="utf-8"
    )
    references = content / "references.yml"
    original = b'existing:\r\n  type: "web"\r\n  title: Existing\r\n'
    references.write_bytes(original)
    spec = _spec(tmp_path)

    assert (
        main(
            [
                "reference",
                "create",
                "--from",
                str(spec),
                "--start",
                str(tmp_path),
                "--format",
                "json",
                "--dry-run",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)

    assert result["dry_run"] is True
    assert "+new-ref:" in result["diff"]
    assert references.read_bytes() == original


def test_reference_create_duplicate_fails_without_modifying_registry(tmp_path: Path, capsys):
    content = tmp_path / "content"
    content.mkdir()
    (tmp_path / "kb-domain.yml").write_text(
        "domain:\n  content_root: content\n", encoding="utf-8"
    )
    references = content / "references.yml"
    original = '# Keep\nexisting:\n  type: "web"\n  title: Existing\n\n'
    references.write_text(original, encoding="utf-8")
    spec = _spec(tmp_path, "id: existing\ntype: book\ntitle: Replacement\n")

    assert (
        main(
            [
                "reference",
                "create",
                "--from",
                str(spec),
                "--start",
                str(tmp_path),
                "--format",
                "json",
            ]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().err)["diagnostics"][0]["code"] == (
        "reference.duplicate.id"
    )
    assert references.read_text(encoding="utf-8") == original


def test_reference_create_dry_run_reports_append_diff_without_writing(
    tmp_path: Path, capsys
):
    content = tmp_path / "content"
    content.mkdir()
    (tmp_path / "kb-domain.yml").write_text(
        "domain:\n  content_root: content\n", encoding="utf-8"
    )
    references = content / "references.yml"
    original = '# Keep\n"existing":\n  type: "web"\n  title: Existing\n\n'
    references.write_text(original, encoding="utf-8")
    spec = _spec(tmp_path)

    assert (
        main(
            [
                "reference",
                "create",
                "--from",
                str(spec),
                "--start",
                str(tmp_path),
                "--format",
                "json",
                "--dry-run",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)

    assert result["dry_run"] is True
    assert "+new-ref:" in result["diff"]
    assert "-# Keep" not in result["diff"]
    assert references.read_text(encoding="utf-8") == original
