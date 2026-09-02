from pathlib import Path
import json

from kb_harness.cli import main
from kb_harness.sync import execute_write_plan, plan_write


def test_write_plan_has_deterministic_diff_and_dry_run_has_no_side_effect(tmp_path: Path):
    target = tmp_path / "note.md"
    target.write_text("old\n", encoding="utf-8")
    plan = plan_write({target: "new\n"})

    assert str(target) in plan.diff
    assert "-old" in plan.diff
    assert "+new" in plan.diff
    assert execute_write_plan(plan, dry_run=True) == []
    assert target.read_text(encoding="utf-8") == "old\n"


def test_write_plan_applies_all_changes_through_one_adapter(tmp_path: Path):
    first = tmp_path / "first.md"
    second = tmp_path / "second.md"
    plan = plan_write({first: "first\n", second: "second\n"})
    calls = []

    def apply(changes):
        calls.append(dict(changes))
        for path, text in changes.items():
            path.write_text(text, encoding="utf-8")
        return list(changes)

    changed = execute_write_plan(plan, apply=apply)

    assert changed == [first, second]
    assert calls == [{first: "first\n", second: "second\n"}]
    assert first.read_text(encoding="utf-8") == "first\n"
    assert second.read_text(encoding="utf-8") == "second\n"


def _claim_project(tmp_path: Path) -> tuple[Path, Path]:
    content = tmp_path / "knowledge"
    people = content / "people"
    claims = content / "claims"
    people.mkdir(parents=True)
    claims.mkdir()
    (tmp_path / "kb-domain.yml").write_text(
        "domain:\n  content_root: knowledge\n", encoding="utf-8"
    )
    (content / "vocabulary.yml").write_text(
        "types:\n  Person:\n    directory: people\n"
        "  Claim:\n    directory: claims\n    graph: false\n"
        "predicates:\n  taught:\n    domain: [Person]\n    range: [Person]\n",
        encoding="utf-8",
    )
    person = (
        "---\n"
        "type: Person\n"
        "title: Person\n"
        "description: Test\n"
        "tags: []\n"
        "timestamp: 2026-01-01T00:00:00Z\n"
        "sources: [x]\n"
        "---\n"
    )
    for name in ("teacher", "student"):
        (people / f"{name}.md").write_text(person, encoding="utf-8")
    return content, claims


def test_claim_create_dry_run_has_relative_diff_and_preserves_kb(tmp_path: Path, capsys):
    _content, claims = _claim_project(tmp_path)
    spec = tmp_path / "claim.yml"
    spec.write_text(
        "subject: /people/teacher.md\n"
        "predicate: taught\n"
        "object: /people/student.md\n"
        "status: proposed\nconfidence: C\nsources: [x]\n",
        encoding="utf-8",
    )

    code = main(
        [
            "claim",
            "create",
            "--from",
            str(spec),
            "--dry-run",
            "--start",
            str(tmp_path),
            "--format",
            "json",
        ]
    )
    result = json.loads(capsys.readouterr().out)

    assert code == 0
    assert result["dry_run"] is True
    assert "a/knowledge/claims/" in result["diff"]
    assert "a/graph.json" in result["diff"]
    assert str(tmp_path) not in result["diff"]
    assert list(claims.glob("*.md")) == []


def test_claim_transition_dry_run_has_relative_diff_and_preserves_claim(
    tmp_path: Path, capsys
):
    _content, claims = _claim_project(tmp_path)
    claim = claims / "example.md"
    original = (
        "---\n"
        "type: Claim\n"
        "title: Example\n"
        "description: Example\n"
        "subject: /people/teacher.md\n"
        "predicate: taught\n"
        "object: /people/student.md\n"
        "status: proposed\nconfidence: C\nsources: [x]\n"
        "tags: []\ntimestamp: 2026-01-01T00:00:00Z\n"
        "---\n"
    )
    claim.write_text(original, encoding="utf-8")

    code = main(
        [
            "claim",
            "transition",
            "claims/example.md",
            "--to",
            "accepted",
            "--dry-run",
            "--start",
            str(tmp_path),
            "--format",
            "json",
        ]
    )
    captured = capsys.readouterr()
    result = json.loads(captured.out or captured.err)

    assert code == 0, result
    assert "a/knowledge/claims/example.md" in result["diff"]
    assert "status: accepted" in result["diff"]
    assert str(tmp_path) not in result["diff"]
    assert claim.read_text(encoding="utf-8") == original
