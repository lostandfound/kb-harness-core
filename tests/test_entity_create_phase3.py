import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from kb_harness.cli import main
from kb_harness.entity import plan_entity_create
from kb_harness.project import Project


class EntityCreatePhase3Test(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        content = self.root / "knowledge"
        (content / "concepts").mkdir(parents=True)
        (self.root / "kb-domain.yml").write_text(
            "domain:\n  content_root: knowledge\n", encoding="utf-8"
        )
        (content / "vocabulary.yml").write_text(
            "types:\n  Concept:\n    directory: concepts\n"
            "    extra_fields: [category]\n"
            "predicates: {}\ntags: [index, science, history]\n",
            encoding="utf-8",
        )
        (content / "concepts" / "index.md").write_text(
            "---\ntype: Index\ntitle: Concepts\ndescription: Concept list.\n"
            "tags: [index]\ntimestamp: 2026-09-01T00:00:00Z\n---\n\n"
            "# Concepts\n\n## エンティティ一覧\n\n", encoding="utf-8"
        )
        (self.root / "entity.yml").write_text(
            "type: Concept\nslug: quantum-theory\ntitle: 量子論\n"
            "description: 物質とエネルギーを量子で説明する理論。\n"
            "tags: [science]\nsources: ['free source']\n"
            "sections:\n  概要: |\n    量子の振る舞いを扱う。\n"
            "  詳細: |\n    歴史的に発展した理論である。\n"
            "  関連項目: |\n    他の理論と関連する。\n"
            "fields:\n  category: physics\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main([*args, "--start", str(self.root), "--format", "json"])
        return code, json.loads(out.getvalue() or err.getvalue())

    def test_create_writes_entity_and_derived_files(self):
        code, result = self.run_cli("entity", "create", "--from", str(self.root / "entity.yml"), "--timestamp", "2026-09-01T00:00:00Z")
        self.assertEqual(code, 0)
        self.assertTrue(result["ok"])
        self.assertIn("knowledge/concepts/quantum-theory.md", result["changed"])
        entity = self.root / "knowledge/concepts/quantum-theory.md"
        self.assertIn("timestamp: 2026-09-01T00:00:00Z", entity.read_text())
        self.assertIn("## 概要\n\n量子の振る舞いを扱う。", entity.read_text())
        validate_code, _ = self.run_cli("validate")
        sync_code, _ = self.run_cli("sync", "--check")
        self.assertEqual(validate_code, 0)
        self.assertEqual(sync_code, 0)

    def test_dry_run_returns_diff_without_writing(self):
        code, result = self.run_cli("entity", "create", "--from", str(self.root / "entity.yml"), "--dry-run")
        self.assertEqual(code, 0)
        self.assertTrue(result["ok"])
        self.assertIn("knowledge/concepts/quantum-theory.md", result["changed"])
        self.assertTrue(result.get("diff"))
        self.assertFalse((self.root / "knowledge/concepts/quantum-theory.md").exists())

    def test_missing_required_spec_is_rejected_without_change(self):
        spec = self.root / "bad.yml"
        spec.write_text("type: Concept\nslug: bad\n", encoding="utf-8")
        code, result = self.run_cli("entity", "create", "--from", str(spec))
        self.assertEqual(code, 2)
        self.assertFalse(result["ok"])
        self.assertFalse((self.root / "knowledge/concepts/bad.md").exists())

    def test_unknown_field_and_wrong_sections_are_rejected(self):
        text = (self.root / "entity.yml").read_text()
        text = text.replace("  category: physics", "  unknown: value")
        bad = self.root / "bad.yml"
        bad.write_text(text.replace("  詳細:", "  余計:", 1), encoding="utf-8")
        code, result = self.run_cli("entity", "create", "--from", str(bad))
        self.assertEqual(code, 1)
        self.assertFalse(result["ok"])
        self.assertFalse((self.root / "knowledge/concepts/quantum-theory.md").exists())

    def test_duplicate_is_nonzero_and_unchanged(self):
        code, _ = self.run_cli("entity", "create", "--from", str(self.root / "entity.yml"))
        self.assertEqual(code, 0)
        entity = self.root / "knowledge/concepts/quantum-theory.md"
        original = entity.read_bytes()
        code, result = self.run_cli("entity", "create", "--from", str(self.root / "entity.yml"))
        self.assertEqual(code, 1)
        self.assertTrue(any("duplicate" in d.get("code", "") for d in result["diagnostics"]))
        self.assertEqual(entity.read_bytes(), original)

    def test_timestamp_cli_override_wins_over_spec(self):
        text = (self.root / "entity.yml").read_text()
        spec = self.root / "time.yml"
        spec.write_text(text + "timestamp: 2025-01-02T03:04:05Z\n", encoding="utf-8")
        code, _ = self.run_cli("entity", "create", "--from", str(spec), "--timestamp", "2026-09-01T00:00:00Z")
        self.assertEqual(code, 0)
        entity = self.root / "knowledge/concepts/quantum-theory.md"
        self.assertIn("timestamp: 2026-09-01T00:00:00Z", entity.read_text())

    def test_timestamp_spec_wins_over_environment(self):
        text = (self.root / "entity.yml").read_text()
        spec = self.root / "time.yml"
        spec.write_text(text + "timestamp: 2025-01-02T03:04:05Z\n", encoding="utf-8")
        with patch.dict(os.environ, {"SOURCE_DATE_EPOCH": "0"}):
            code, _ = self.run_cli("entity", "create", "--from", str(spec))
        self.assertEqual(code, 0)
        self.assertIn("timestamp: 2025-01-02T03:04:05Z", (self.root / "knowledge/concepts/quantum-theory.md").read_text())

    def test_timestamp_environment_wins_over_injected_clock(self):
        text = (self.root / "entity.yml").read_text().replace("quantum-theory", "epoch-example")
        spec = self.root / "epoch.yml"
        spec.write_text(text, encoding="utf-8")
        project = Project.discover(self.root)
        with patch.dict(os.environ, {"SOURCE_DATE_EPOCH": "0"}):
            plan = plan_entity_create(
                project,
                spec,
                clock=lambda: datetime(2030, 1, 1, tzinfo=timezone.utc),
            )
        self.assertIn("timestamp: 1970-01-01T00:00:00Z", plan.changes[next(path for path in plan.changes if path.name == "epoch-example.md")])

    def test_timestamp_injected_clock_is_used_without_environment(self):
        text = (self.root / "entity.yml").read_text().replace("quantum-theory", "clock-example")
        spec = self.root / "clock.yml"
        spec.write_text(text, encoding="utf-8")
        project = Project.discover(self.root)
        with patch.dict(os.environ, {}, clear=True):
            plan = plan_entity_create(
                project,
                spec,
                clock=lambda: datetime(2030, 1, 1, 1, 2, 3, tzinfo=timezone.utc),
            )
        self.assertIn("timestamp: 2030-01-01T01:02:03Z", plan.changes[next(path for path in plan.changes if path.name == "clock-example.md")])

    def test_staging_copies_only_content_tree(self):
        content = self.root / "knowledge"
        (self.root / ".git").mkdir()
        (self.root / "packages").mkdir()
        (self.root / "corpus").mkdir()
        original_copytree = __import__("shutil").copytree
        with patch("kb_harness.entity.shutil.copytree", wraps=original_copytree) as copytree:
            plan_entity_create(Project.discover(self.root), self.root / "entity.yml")
        top_level_sources = [Path(call.args[0]).resolve() for call in copytree.call_args_list if call.args]
        self.assertEqual(top_level_sources[0], content.resolve())
        self.assertNotIn(self.root.resolve(), top_level_sources)


if __name__ == "__main__":
    unittest.main()
