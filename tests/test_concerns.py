"""懸念台帳: 1 件 1 YAML、実在する対象の必須化、kb validate / kb sync / kb concern。"""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from kb_harness.cli import main
from kb_harness.concerns import (
    ConcernError,
    load_concern,
    render_concerns_index,
    validate_concerns,
)
from kb_harness.entity import plan_entity_create
from kb_harness.project import Project, ProjectError
from kb_harness.sync import apply_changes_atomically, plan_sync


ROOT = Path(__file__).resolve().parents[1]

VOCABULARY = (
    "types:\n"
    "  Concept:\n    directory: concepts\n"
    "predicates:\n"
    "  related-to:\n    description: 汎用\n    domain: [Concept]\n    range: [Concept]\n"
    "tags:\n  - cs\n"
)

VALID = (
    "targets: [/concepts/paxos.md, 'ref: lamport-1998']\n"
    "kind: conflict\n"
    "status: settled-hedged\n"
    "summary: 原論文の最初の投稿年が資料で食い違う（1989 / 1990）\n"
    "sources: ['ref: lamport-1998']\n"
    "resolution: 本文は両論を併記した\n"
)


def _entity(slug: str, title: str) -> str:
    return (
        f"---\ntype: Concept\ntitle: {title}\ndescription: {title} の説明である。\n"
        f"tags: [cs]\ntimestamp: 2026-09-01T00:00:00Z\nsources: ['ref: lamport-1998']\nrelations: []\n"
        f"---\n\n## 概要\n\n本文。\n"
    )


def build_kb(root: Path, *, concerns: bool = True) -> Project:
    content = root / "knowledge"
    (content / "concepts").mkdir(parents=True)
    (content / "concepts" / "index.md").write_text(
        "---\ntype: Index\ntitle: concepts\ndescription: 一覧である。\ntags: []\n"
        "timestamp: 2026-09-01T00:00:00Z\n---\n\n## エンティティ一覧\n\n",
        encoding="utf-8",
    )
    (content / "vocabulary.yml").write_text(VOCABULARY, encoding="utf-8")
    (content / "references.yml").write_text(
        "lamport-1998:\n  type: web\n  title: The Part-Time Parliament\n  url: https://example.com/paxos\n",
        encoding="utf-8",
    )
    (content / "concepts" / "paxos.md").write_text(_entity("paxos", "Paxos"), encoding="utf-8")
    (content / "concepts" / "raft.md").write_text(_entity("raft", "Raft"), encoding="utf-8")
    config = "domain:\n  content_root: knowledge\n"
    if concerns:
        config += "concerns:\n  root: concerns\n"
    (root / "kb-domain.yml").write_text(config, encoding="utf-8")
    (root / "concerns").mkdir()
    (root / "concerns" / "paxos-first-submission.yml").write_text(VALID, encoding="utf-8")
    project = Project.discover(root)
    apply_changes_atomically(plan_sync(project))
    return project


def run_cli(*args: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(list(args))
    return code, out.getvalue(), err.getvalue()


class ConcernTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.project = build_kb(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, name: str, text: str) -> Path:
        path = self.root / "concerns" / name
        path.write_text(text, encoding="utf-8")
        return path

    def errors(self) -> list[str]:
        return validate_concerns(self.project.content_root, self.project.concerns_root)


class TestProjectConfig(unittest.TestCase):
    def test_concerns_section_resolves_root_and_default_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = build_kb(Path(tmp))
            self.assertEqual(project.concerns_root, (Path(tmp) / "concerns").resolve())
            self.assertEqual(project.concerns_index, (Path(tmp) / "concerns" / "index.md").resolve())

    def test_absent_section_disables_concerns(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = build_kb(Path(tmp), concerns=False)
            self.assertIsNone(project.concerns_root)

    def test_root_inside_content_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build_kb(root)
            (root / "kb-domain.yml").write_text(
                "domain:\n  content_root: knowledge\nconcerns:\n  root: knowledge/concerns\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ProjectError, "concerns.root must not be inside domain.content_root"):
                Project.discover(root)

    def test_root_shared_with_views_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build_kb(root)
            (root / "kb-domain.yml").write_text(
                "domain:\n  content_root: knowledge\nviews:\n  root: notes\nconcerns:\n  root: notes\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ProjectError, "must differ from views"):
                Project.discover(root)


class TestLoadConcern(ConcernTestCase):
    def test_valid_concern(self):
        concern = load_concern(self.root / "concerns" / "paxos-first-submission.yml")
        self.assertEqual(concern.targets, ("/concepts/paxos.md", "ref: lamport-1998"))
        self.assertEqual(concern.kind, "conflict")
        self.assertFalse(concern.actionable)
        self.assertEqual(self.errors(), [])

    def test_targets_are_required(self):
        # 目的外の利用（作業の予定・ハーネスの問題）を構造で拒む核
        path = self.write("task.yml", "kind: judgment\nstatus: open\nsummary: OLAP キューブを追加する\n")
        with self.assertRaisesRegex(ConcernError, "'targets' is required.*BACKLOG"):
            load_concern(path)

    def test_unknown_key_is_rejected(self):
        path = self.write("extra.yml", VALID + "priority: high\n")
        with self.assertRaisesRegex(ConcernError, "unknown key\\(s\\): priority"):
            load_concern(path)

    def test_kind_outside_vocabulary_is_rejected(self):
        # 型や境界の判断（modeling）は懸念の種別に無い
        path = self.write("modeling.yml", VALID.replace("kind: conflict", "kind: modeling"))
        with self.assertRaisesRegex(ConcernError, "kind must be one of"):
            load_concern(path)

    def test_status_outside_vocabulary_is_rejected(self):
        path = self.write("status.yml", VALID.replace("status: settled-hedged", "status: done"))
        with self.assertRaisesRegex(ConcernError, "status must be one of"):
            load_concern(path)

    def test_status_specific_field_is_required(self):
        cases = {
            "resolved": "resolution",
            "settled-hedged": "resolution",
            "blocked-source": "awaiting",
            "suspended": "resume_when",
        }
        for status, field in cases.items():
            with self.subTest(status=status):
                path = self.write(
                    "s.yml",
                    f"targets: [/concepts/paxos.md]\nkind: indirect\nstatus: {status}\nsummary: 孫引き\n",
                )
                with self.assertRaisesRegex(ConcernError, f"status '{status}' requires '{field}'"):
                    load_concern(path)

    def test_status_field_on_other_status_is_rejected(self):
        path = self.write(
            "s.yml",
            "targets: [/concepts/paxos.md]\nkind: indirect\nstatus: open\nsummary: 孫引き\nresolution: 済み\n",
        )
        with self.assertRaisesRegex(ConcernError, "'resolution' is only for status settled-hedged / resolved"):
            load_concern(path)


class TestValidateConcerns(ConcernTestCase):
    def test_missing_entity_target(self):
        self.write("gone.yml", VALID.replace("/concepts/paxos.md", "/concepts/renamed.md"))
        self.assertTrue(any("'/concepts/renamed.md' does not exist" in e for e in self.errors()))

    def test_bare_slug_target(self):
        self.write("slug.yml", VALID.replace("/concepts/paxos.md", "paxos"))
        self.assertTrue(any("'/dir/file.md' か 'ref: <id>'" in e for e in self.errors()))

    def test_missing_reference_target_and_source(self):
        self.write("ref.yml", VALID.replace("lamport-1998", "nowhere"))
        errors = self.errors()
        self.assertTrue(any("targets の 'ref: nowhere'" in e for e in errors))
        self.assertTrue(any("sources の 'ref: nowhere'" in e for e in errors))

    def test_index_target_is_rejected(self):
        self.write("index-target.yml", VALID.replace("/concepts/paxos.md", "/concepts/index.md"))
        self.assertTrue(any("'/concepts/index.md' does not exist" in e for e in self.errors()))

    def test_duplicate_target(self):
        self.write("dup.yml", VALID.replace("'ref: lamport-1998']\nkind", "/concepts/paxos.md]\nkind"))
        self.assertTrue(any("が重複している" in e for e in self.errors()))

    def test_duplicate_id_and_bad_filename(self):
        self.write("paxos-first-submission.yaml", VALID)
        self.write("Bad_Name.yml", VALID)
        errors = self.errors()
        self.assertTrue(any("concern id 'paxos-first-submission' が重複" in e for e in errors))
        self.assertTrue(any("ケバブケース" in e for e in errors))


class TestIndex(ConcernTestCase):
    def test_index_groups_by_status_and_links_relatively(self):
        self.write(
            "raft-origin.yml",
            "targets: [/concepts/raft.md]\nkind: weak-source\nstatus: open\nsummary: 出典が 1 系統しかない\n",
        )
        text = render_concerns_index(self.project.content_root, self.project.concerns_root)
        self.assertLess(text.index("## 未着手（open）"), text.index("## 決着せず記述側は完了（settled-hedged）"))
        self.assertIn("[Raft](../knowledge/concepts/raft.md)", text)
        self.assertIn("`ref: lamport-1998`", text)
        self.assertIn("[paxos-first-submission](paxos-first-submission.yml)", text)
        self.assertIn("  - 対応: 本文は両論を併記した", text)

    def test_sync_check_reports_stale_index(self):
        self.write(
            "raft-origin.yml",
            "targets: [/concepts/raft.md]\nkind: weak-source\nstatus: open\nsummary: 出典が 1 系統しかない\n",
        )
        code, out, _err = run_cli("sync", "--check", "--start", str(self.root), "--format", "json")
        self.assertEqual(code, 1)
        codes = {d["code"] for d in json.loads(out)["diagnostics"]}
        self.assertEqual(codes, {"concerns.stale"})
        self.assertEqual(run_cli("sync", "--start", str(self.root))[0], 0)
        self.assertEqual(run_cli("sync", "--check", "--start", str(self.root))[0], 0)

    def test_sync_reports_broken_definition_as_diagnostic(self):
        self.write("broken.yml", "kind: conflict\n")
        code, out, _err = run_cli("sync", "--start", str(self.root), "--format", "json")
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["diagnostics"][0]["code"], "concern.spec")


class TestCli(ConcernTestCase):
    def test_validate_includes_concerns(self):
        self.assertEqual(run_cli("validate", "--start", str(self.root))[0], 0)
        self.write("gone.yml", VALID.replace("/concepts/paxos.md", "/concepts/renamed.md"))
        code, out, _err = run_cli("validate", "--start", str(self.root), "--format", "json")
        self.assertEqual(code, 1)
        self.assertTrue(any("renamed.md" in d["message"] for d in json.loads(out)["diagnostics"]))

    def test_legacy_ledger_warns(self):
        (self.root / "docs").mkdir()
        (self.root / "docs" / "CONCERNS.md").write_text("# CONCERNS\n", encoding="utf-8")
        code, out, _err = run_cli("validate", "--start", str(self.root), "--format", "json")
        self.assertEqual(code, 0)
        codes = [w["code"] for w in json.loads(out)["warnings"]]
        self.assertIn("concern.legacy_ledger", codes)

    def test_list_filters(self):
        self.write(
            "raft-origin.yml",
            "targets: [/concepts/raft.md]\nkind: weak-source\nstatus: open\nsummary: 出典が 1 系統しかない\n",
        )
        _code, out, _err = run_cli("concern", "list", "--start", str(self.root), "--format", "json")
        self.assertEqual([c["id"] for c in json.loads(out)["concerns"]], ["paxos-first-submission", "raft-origin"])
        _code, out, _err = run_cli("concern", "list", "--actionable", "--start", str(self.root), "--format", "json")
        self.assertEqual([c["id"] for c in json.loads(out)["concerns"]], ["raft-origin"])
        _code, out, _err = run_cli(
            "concern", "list", "--for", "ref:lamport-1998", "--start", str(self.root), "--format", "json"
        )
        self.assertEqual([c["id"] for c in json.loads(out)["concerns"]], ["paxos-first-submission"])
        entity_file = str(self.root / "knowledge" / "concepts" / "raft.md")
        _code, out, _err = run_cli("concern", "list", "--for", entity_file, "--start", str(self.root), "--format", "json")
        self.assertEqual([c["id"] for c in json.loads(out)["concerns"]], ["raft-origin"])

    def test_list_for_outside_content_root(self):
        code, out, _err = run_cli(
            "concern", "list", "--for", str(self.root / "kb-domain.yml"), "--start", str(self.root), "--format", "json"
        )
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["diagnostics"][0]["code"], "concern.arguments")

    def test_summary(self):
        _code, out, _err = run_cli("concern", "summary", "--start", str(self.root), "--format", "json")
        summary = json.loads(out)
        self.assertEqual(summary["total"], 1)
        self.assertEqual(summary["by_status"]["settled-hedged"], 1)
        self.assertEqual(summary["by_kind"]["conflict"], 1)
        self.assertEqual(summary["actionable"], 0)

    def test_disabled_without_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_kb(Path(tmp), concerns=False)
            code, out, _err = run_cli("concern", "list", "--start", tmp, "--format", "json")
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(out)["diagnostics"][0]["code"], "concern.disabled")


class TestEntityCreateStaging(ConcernTestCase):
    def test_entity_create_keeps_concerns_index_fresh(self):
        spec = self.root / "spec.yml"
        spec.write_text(
            "type: Concept\nslug: multi-paxos\ntitle: Multi-Paxos\ndescription: Multi-Paxos の説明である。\n"
            "tags: [cs]\nsources: ['ref: lamport-1998']\n"
            "sections:\n  概要: 概要である。\n  詳細: 詳細である。\n  関連項目: なし。\n",
            encoding="utf-8",
        )
        plan = plan_entity_create(self.project, spec, timestamp="2026-09-02T00:00:00Z")
        apply_changes_atomically(plan.changes)
        self.assertEqual(plan_sync(self.project), {})

    def test_entity_create_fails_on_broken_concern(self):
        self.write("gone.yml", VALID.replace("/concepts/paxos.md", "/concepts/renamed.md"))
        spec = self.root / "spec.yml"
        spec.write_text(
            "type: Concept\nslug: multi-paxos\ntitle: Multi-Paxos\ndescription: Multi-Paxos の説明である。\n"
            "tags: [cs]\nsources: ['ref: lamport-1998']\n"
            "sections:\n  概要: 概要である。\n  詳細: 詳細である。\n  関連項目: なし。\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(Exception, "renamed.md"):
            plan_entity_create(self.project, spec, timestamp="2026-09-02T00:00:00Z")


class TestConcernsSummaryScript(ConcernTestCase):
    def test_script_reads_structured_ledger(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "concerns_summary.py")],
            cwd=self.root,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("懸念 1件", result.stdout)
        self.assertIn("settled-hedged: 1", result.stdout)

    def test_script_keeps_markdown_ledger_when_unconfigured(self):
        (self.root / "kb-domain.yml").write_text("domain:\n  content_root: knowledge\n", encoding="utf-8")
        (self.root / "docs").mkdir()
        (self.root / "docs" / "CONCERNS.md").write_text(
            "- [ ] paxos: 投稿年の食い違い。 status: open\n", encoding="utf-8"
        )
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "concerns_summary.py"), "--actionable"],
            cwd=self.root,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[open] paxos", result.stdout)


if __name__ == "__main__":
    unittest.main()
