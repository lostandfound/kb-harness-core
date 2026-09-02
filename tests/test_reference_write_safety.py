from __future__ import annotations

import json
from pathlib import Path

from kb_harness.cli import main


def _project(tmp_path: Path) -> Path:
    (tmp_path / "content").mkdir()
    (tmp_path / "kb-domain.yml").write_text(
        "domain:\n  content_root: content\n", encoding="utf-8"
    )
    (tmp_path / "search.json").write_text(
        '{"results": [{"title": "Karate", "authors": ["Alice"], '
        '"year": "1915", "url": "https://example.test/karate"}]}',
        encoding="utf-8",
    )
    return tmp_path


def test_reference_spec_dry_run_plans_diff_without_writing(tmp_path: Path, capsys):
    root = _project(tmp_path)
    output = root / "content" / "reference.yml"

    code = main(
        [
            "reference",
            "spec",
            "--from",
            str(root / "search.json"),
            "--output",
            "content/reference.yml",
            "--start",
            str(root),
            "--format",
            "json",
            "--dry-run",
        ]
    )

    result = json.loads(capsys.readouterr().out)
    assert code == 0
    assert result["dry_run"] is True
    assert "Karate" in result["diff"]
    assert not output.exists()


def test_reference_spec_rejects_existing_output_without_force(tmp_path: Path, capsys):
    root = _project(tmp_path)
    output = root / "content" / "reference.yml"
    output.write_text("original\n", encoding="utf-8")

    code = main(
        [
            "reference",
            "spec",
            "--from",
            str(root / "search.json"),
            "--output",
            "content/reference.yml",
            "--start",
            str(root),
            "--format",
            "json",
        ]
    )

    result = json.loads(capsys.readouterr().err)
    assert code == 2
    assert result["diagnostics"][0]["code"] == "reference.output.exists"
    assert output.read_text(encoding="utf-8") == "original\n"


def test_reference_spec_force_replaces_existing_output(tmp_path: Path, capsys):
    root = _project(tmp_path)
    output = root / "content" / "reference.yml"
    output.write_text("original\n", encoding="utf-8")

    code = main(
        [
            "reference",
            "spec",
            "--from",
            str(root / "search.json"),
            "--output",
            "content/reference.yml",
            "--force",
            "--start",
            str(root),
            "--format",
            "json",
        ]
    )

    result = json.loads(capsys.readouterr().out)
    assert code == 0
    assert result["changed"] == ["content/reference.yml"]
    assert "Karate" in output.read_text(encoding="utf-8")


def test_reference_spec_allows_new_nested_output_inside_project(tmp_path: Path, capsys):
    root = _project(tmp_path)
    output = root / "generated" / "references" / "reference.yml"

    code = main(
        [
            "reference",
            "spec",
            "--from",
            str(root / "search.json"),
            "--output",
            "generated/references/reference.yml",
            "--start",
            str(root),
            "--format",
            "json",
        ]
    )

    result = json.loads(capsys.readouterr().out)
    assert code == 0
    assert result["changed"] == ["generated/references/reference.yml"]
    assert output.exists()


def test_reference_spec_rejects_output_outside_project(tmp_path: Path, capsys):
    root = _project(tmp_path)
    outside = tmp_path.parent / "outside-reference.yml"

    code = main(
        [
            "reference",
            "spec",
            "--from",
            str(root / "search.json"),
            "--output",
            str(outside),
            "--start",
            str(root),
            "--format",
            "json",
        ]
    )

    result = json.loads(capsys.readouterr().err)
    assert code == 2
    assert result["diagnostics"][0]["code"] == "reference.output.outside_project"
    assert not outside.exists()


def test_reference_spec_rejects_symlink_escape(tmp_path: Path, capsys):
    root = _project(tmp_path)
    outside = tmp_path.parent / "outside"
    outside.mkdir()
    (root / "content" / "out.yml").symlink_to((outside / "out.yml").resolve())

    code = main(
        [
            "reference",
            "spec",
            "--from",
            str(root / "search.json"),
            "--output",
            "content/out.yml",
            "--start",
            str(root),
            "--format",
            "json",
        ]
    )

    result = json.loads(capsys.readouterr().err)
    assert code == 2
    assert result["diagnostics"][0]["code"] == "reference.output.outside_project"
    assert not (outside / "out.yml").exists()


def test_reference_spec_apply_failure_is_internal_and_output_unchanged(
    tmp_path: Path, capsys, monkeypatch
):
    root = _project(tmp_path)
    output = root / "content" / "reference.yml"
    output.write_text("original\n", encoding="utf-8")

    def fail(*_args, **_kwargs):
        raise OSError("simulated write failure")

    monkeypatch.setattr("kb_harness.cli.apply_changes_atomically", fail)
    code = main(
        [
            "reference",
            "spec",
            "--from",
            str(root / "search.json"),
            "--output",
            "content/reference.yml",
            "--force",
            "--start",
            str(root),
            "--format",
            "json",
        ]
    )

    result = json.loads(capsys.readouterr().out)
    assert code == 3
    assert result["diagnostics"][0]["code"] == "internal.error"
    assert output.read_text(encoding="utf-8") == "original\n"


def test_cli_boundary_structures_unexpected_reference_failure(
    tmp_path: Path, capsys, monkeypatch
):
    root = _project(tmp_path)

    def fail(*_args, **_kwargs):
        raise RuntimeError("unexpected failure")

    monkeypatch.setattr("kb_harness.cli.reference_health", fail)
    code = main(
        ["reference", "health", "--start", str(root), "--format", "json"]
    )

    result = json.loads(capsys.readouterr().out)
    assert code == 3
    assert result["diagnostics"][0]["code"] == "internal.error"
