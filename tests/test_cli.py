import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from kb_harness.cli import main
from kb_harness.graph import render_graph


class CliTest(unittest.TestCase):
    def test_index_build_returns_internal_error_and_rolls_back_atomically(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            content = root / "knowledge"
            notes = content / "notes"
            people = content / "people"
            notes.mkdir(parents=True)
            people.mkdir()
            (root / "kb-domain.yml").write_text(
                "domain:\n  content_root: knowledge\n", encoding="utf-8"
            )
            (content / "vocabulary.yml").write_text(
                "types:\n  Note:\n    directory: notes\n    graph: false\n"
                "  Person:\n    directory: people\n    graph: false\n",
                encoding="utf-8",
            )
            note_index = notes / "index.md"
            person_index = people / "index.md"
            note_index.write_text("notes original\n", encoding="utf-8")
            person_index.write_text("people original\n", encoding="utf-8")
            for directory, name in ((notes, "note"), (people, "person")):
                (directory / f"{name}.md").write_text(
                    f"---\ntype: {('Note' if directory == notes else 'Person')}\n"
                    f"title: {name}\ndescription: Description.\n---\n\nBody\n",
                    encoding="utf-8",
                )

            original_replace = Path.replace
            calls = 0

            def fail_on_second(source: Path, target: Path) -> Path:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("simulated replacement failure")
                return original_replace(source, target)

            output = io.StringIO()
            with patch("kb_harness.sync.Path.replace", side_effect=fail_on_second):
                with redirect_stdout(output):
                    exit_code = main(
                        ["index", "build", "--start", str(root), "--format", "json"]
                    )

            result = json.loads(output.getvalue())
            self.assertEqual(exit_code, 3)
            self.assertFalse(result["ok"])
            self.assertEqual(result["diagnostics"][0]["code"], "internal.error")
            self.assertEqual(note_index.read_text(encoding="utf-8"), "notes original\n")
            self.assertEqual(person_index.read_text(encoding="utf-8"), "people original\n")

    def test_project_show_outputs_machine_readable_paths(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            (root / "knowledge").mkdir()
            (root / "kb-domain.yml").write_text(
                "domain:\n  content_root: knowledge\n",
                encoding="utf-8",
            )
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = main(
                    ["project", "show", "--start", str(root), "--format", "json"]
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(
                json.loads(output.getvalue()),
                {
                    "content_root": str((root / "knowledge").resolve()),
                    "repo_root": str(root.resolve()),
                },
            )

    def test_project_error_uses_stable_json_diagnostic_and_exit_two(self):
        with tempfile.TemporaryDirectory() as tempdir:
            error_output = io.StringIO()

            with redirect_stderr(error_output):
                exit_code = main(
                    ["project", "show", "--start", tempdir, "--format", "json"]
                )

            diagnostic = json.loads(error_output.getvalue())
            self.assertEqual(exit_code, 2)
            self.assertEqual(diagnostic["diagnostics"][0]["code"], "project.not_found")
            self.assertFalse(diagnostic["ok"])

    def test_unexpected_project_error_uses_internal_exit_three(self):
        output = io.StringIO()
        with patch("kb_harness.cli.Project.discover", side_effect=RuntimeError("boom")):
            with redirect_stdout(output):
                exit_code = main(["validate", "--format", "json"])
        result = json.loads(output.getvalue())
        self.assertEqual(exit_code, 3)
        self.assertEqual(result["diagnostics"][0]["code"], "internal.error")

    def test_validate_outputs_success_json_for_valid_kb(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            content = root / "knowledge"
            content.mkdir()
            (root / "kb-domain.yml").write_text(
                "domain:\n  content_root: knowledge\n",
                encoding="utf-8",
            )
            (content / "vocabulary.yml").write_text(
                "types:\n  Note:\n    directory: notes\n    graph: false\n"
                "predicates: {}\ntags: []\n",
                encoding="utf-8",
            )
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = main(
                    ["validate", "--start", str(root), "--format", "json"]
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(
                json.loads(output.getvalue()),
                {"changed": [], "diagnostics": [], "ok": True, "warnings": []},
            )

    def test_validate_check_urls_reports_unreachable_source_url(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            content = root / "knowledge"
            notes = content / "notes"
            notes.mkdir(parents=True)
            (root / "kb-domain.yml").write_text(
                "domain:\n  content_root: knowledge\n",
                encoding="utf-8",
            )
            (content / "vocabulary.yml").write_text(
                "types:\n  Note:\n    directory: notes\n    graph: false\n"
                "predicates: {}\ntags: []\n",
                encoding="utf-8",
            )
            (notes / "note.md").write_text(
                "---\ntype: Note\ntitle: note\ndescription: Description.\n"
                "sources:\n  - https://example.invalid/page\n---\n\nBody\n",
                encoding="utf-8",
            )
            output = io.StringIO()

            with patch("kb_harness.validation._url_reachable", return_value=False) as reachable:
                with redirect_stdout(output):
                    exit_code = main(
                        ["validate", "--check-urls", "--start", str(root), "--format", "json"]
                    )

            result = json.loads(output.getvalue())
            reachable.assert_called_once_with("https://example.invalid/page")
            self.assertEqual(exit_code, 1)
            self.assertIn("unreachable URL", result["diagnostics"][-1]["message"])

    def test_validate_outputs_structured_diagnostic_and_exit_one(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            content = root / "knowledge"
            notes = content / "notes"
            notes.mkdir(parents=True)
            (root / "kb-domain.yml").write_text(
                "domain:\n  content_root: knowledge\n",
                encoding="utf-8",
            )
            (content / "vocabulary.yml").write_text(
                "types:\n  Note:\n    directory: notes\n    graph: false\n"
                "predicates: {}\ntags: []\n",
                encoding="utf-8",
            )
            (notes / "broken.md").write_text("missing frontmatter", encoding="utf-8")
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = main(
                    ["validate", "--start", str(root), "--format", "json"]
                )

            result = json.loads(output.getvalue())
            self.assertEqual(exit_code, 1)
            self.assertFalse(result["ok"])
            self.assertEqual(result["diagnostics"][0]["code"], "validation.error")
            self.assertIn("frontmatter", result["diagnostics"][0]["message"])

    def test_index_check_reports_stale_file_without_writing(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            content = root / "knowledge"
            notes = content / "notes"
            notes.mkdir(parents=True)
            (root / "kb-domain.yml").write_text(
                "domain:\n  content_root: knowledge\n",
                encoding="utf-8",
            )
            (content / "vocabulary.yml").write_text(
                "types:\n  Note:\n    directory: notes\n    graph: false\n",
                encoding="utf-8",
            )
            index = notes / "index.md"
            original = "# Notes\n\n## エンティティ一覧\n\n"
            index.write_text(original, encoding="utf-8")
            (notes / "example.md").write_text(
                "---\ntype: Note\ntitle: Example\ndescription: Description.\n"
                "tags: []\ntimestamp: 2026-09-01T00:00:00Z\nsources: []\n"
                "---\n\nBody\n",
                encoding="utf-8",
            )
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = main(
                    ["index", "check", "--start", str(root), "--format", "json"]
                )

            result = json.loads(output.getvalue())
            self.assertEqual(exit_code, 1)
            self.assertEqual(index.read_text(encoding="utf-8"), original)
            self.assertEqual(result["diagnostics"][0]["code"], "index.stale")

    def test_index_build_writes_planned_change(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            content = root / "knowledge"
            notes = content / "notes"
            notes.mkdir(parents=True)
            (root / "kb-domain.yml").write_text(
                "domain:\n  content_root: knowledge\n",
                encoding="utf-8",
            )
            (content / "vocabulary.yml").write_text(
                "types:\n  Note:\n    directory: notes\n    graph: false\n",
                encoding="utf-8",
            )
            index = notes / "index.md"
            index.write_text("# Notes\n\n## エンティティ一覧\n\n", encoding="utf-8")
            (notes / "example.md").write_text(
                "---\ntype: Note\ntitle: Example\ndescription: Description.\n"
                "tags: []\ntimestamp: 2026-09-01T00:00:00Z\nsources: []\n"
                "---\n\nBody\n",
                encoding="utf-8",
            )
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = main(
                    ["index", "build", "--start", str(root), "--format", "json"]
                )

            result = json.loads(output.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(result["changed"], ["knowledge/notes/index.md"])
            self.assertIn("[Example](/notes/example.md)", index.read_text(encoding="utf-8"))

    def test_graph_check_reports_stale_graph_without_writing(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            content = root / "knowledge"
            content.mkdir()
            (root / "kb-domain.yml").write_text(
                "domain:\n  content_root: knowledge\n",
                encoding="utf-8",
            )
            (content / "vocabulary.yml").write_text(
                "types:\n  Note:\n    directory: notes\n    graph: false\n",
                encoding="utf-8",
            )
            graph = root / "graph.json"
            graph.write_text("{}\n", encoding="utf-8")
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = main(
                    ["graph", "check", "--start", str(root), "--format", "json"]
                )

            result = json.loads(output.getvalue())
            self.assertEqual(exit_code, 1)
            self.assertEqual(graph.read_text(encoding="utf-8"), "{}\n")
            self.assertEqual(result["diagnostics"][0]["code"], "graph.stale")

    def test_graph_build_writes_canonical_graph(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            content = root / "knowledge"
            content.mkdir()
            (root / "kb-domain.yml").write_text(
                "domain:\n  content_root: knowledge\n",
                encoding="utf-8",
            )
            (content / "vocabulary.yml").write_text(
                "types:\n  Note:\n    directory: notes\n    graph: false\n",
                encoding="utf-8",
            )
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = main(
                    ["graph", "build", "--start", str(root), "--format", "json"]
                )

            result = json.loads(output.getvalue())
            graph = root / "graph.json"
            self.assertEqual(exit_code, 0)
            self.assertEqual(result["changed"], ["graph.json"])
            self.assertEqual(json.loads(graph.read_text(encoding="utf-8"))["claims"], [])

    def test_sync_check_reports_index_and_graph_without_writing(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            content = root / "knowledge"
            notes = content / "notes"
            notes.mkdir(parents=True)
            (root / "kb-domain.yml").write_text(
                "domain:\n  content_root: knowledge\n",
                encoding="utf-8",
            )
            (content / "vocabulary.yml").write_text(
                "types:\n  Note:\n    directory: notes\n    graph: false\n",
                encoding="utf-8",
            )
            index = notes / "index.md"
            index_original = "# Notes\n\n## エンティティ一覧\n\n"
            index.write_text(index_original, encoding="utf-8")
            (notes / "example.md").write_text(
                "---\ntype: Note\ntitle: Example\ndescription: Description.\n"
                "tags: []\ntimestamp: 2026-09-01T00:00:00Z\nsources: []\n"
                "---\n\nBody\n",
                encoding="utf-8",
            )
            graph = root / "graph.json"
            graph.write_text("{}\n", encoding="utf-8")
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = main(
                    ["sync", "--check", "--start", str(root), "--format", "json"]
                )

            result = json.loads(output.getvalue())
            self.assertEqual(exit_code, 1)
            self.assertEqual(index.read_text(encoding="utf-8"), index_original)
            self.assertEqual(graph.read_text(encoding="utf-8"), "{}\n")
            self.assertEqual(
                [item["code"] for item in result["diagnostics"]],
                ["graph.stale", "index.stale"],
            )

    def test_sync_build_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            content = root / "knowledge"
            content.mkdir()
            (root / "kb-domain.yml").write_text(
                "domain:\n  content_root: knowledge\n",
                encoding="utf-8",
            )
            (content / "vocabulary.yml").write_text(
                "types:\n  Note:\n    directory: notes\n    graph: false\n",
                encoding="utf-8",
            )
            first_output = io.StringIO()

            with redirect_stdout(first_output):
                first_exit = main(
                    ["sync", "--start", str(root), "--format", "json"]
                )
            first_result = json.loads(first_output.getvalue())

            check_output = io.StringIO()
            with redirect_stdout(check_output):
                check_exit = main(
                    ["sync", "--check", "--start", str(root), "--format", "json"]
                )
            check_result = json.loads(check_output.getvalue())

            self.assertEqual(first_exit, 0)
            self.assertEqual(first_result["changed"], ["graph.json"])
            self.assertEqual(check_exit, 0)
            self.assertTrue(check_result["ok"])
            self.assertEqual(check_result["diagnostics"], [])

    def test_doctor_reports_healthy_synchronized_project(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            content = root / "knowledge"
            content.mkdir()
            (root / "kb-domain.yml").write_text(
                "domain:\n  content_root: knowledge\n",
                encoding="utf-8",
            )
            (content / "vocabulary.yml").write_text(
                "types:\n  Note:\n    directory: notes\n    graph: false\n",
                encoding="utf-8",
            )
            (root / "graph.json").write_text(render_graph(content), encoding="utf-8")
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = main(
                    ["doctor", "--start", str(root), "--format", "json"]
                )

            result = json.loads(output.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertTrue(result["ok"])
            # kb-ontology-core が無い環境では警告が 1 件出るが、それは正常
            self.assertEqual([d for d in result["diagnostics"] if d["code"] != "doctor.ontology.not_installed"], [])
            self.assertIn("kb_harness_version", result["details"])

    def test_index_check_returns_zero_when_indexes_are_current(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            content = root / "knowledge"
            content.mkdir()
            (root / "kb-domain.yml").write_text(
                "domain:\n  content_root: knowledge\n", encoding="utf-8"
            )
            (content / "vocabulary.yml").write_text(
                "types:\n  Note:\n    directory: notes\n    graph: false\n",
                encoding="utf-8",
            )
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(
                    ["index", "check", "--start", str(root), "--format", "json"]
                )
            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(output.getvalue())["diagnostics"], [])

    def test_graph_check_returns_zero_when_graph_is_current(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            content = root / "knowledge"
            content.mkdir()
            (root / "kb-domain.yml").write_text(
                "domain:\n  content_root: knowledge\n", encoding="utf-8"
            )
            (content / "vocabulary.yml").write_text(
                "types:\n  Note:\n    directory: notes\n    graph: false\n",
                encoding="utf-8",
            )
            (root / "graph.json").write_text(render_graph(content), encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(
                    ["graph", "check", "--start", str(root), "--format", "json"]
                )
            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(output.getvalue())["diagnostics"], [])

    def test_doctor_reports_stale_generated_file(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            content = root / "knowledge"
            content.mkdir()
            (root / "kb-domain.yml").write_text(
                "domain:\n  content_root: knowledge\n", encoding="utf-8"
            )
            (content / "vocabulary.yml").write_text(
                "types:\n  Note:\n    directory: notes\n    graph: false\n",
                encoding="utf-8",
            )
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(
                    ["doctor", "--start", str(root), "--format", "json"]
                )
            result = json.loads(output.getvalue())
            self.assertEqual(exit_code, 1)
            self.assertIn("doctor.generated_stale", [d["code"] for d in result["diagnostics"]])


if __name__ == "__main__":
    unittest.main()


class TagIndexCliTest(unittest.TestCase):
    def _build(self, root: Path) -> Path:
        content = root / "knowledge"
        (content / "notes").mkdir(parents=True)
        (root / "kb-domain.yml").write_text(
            "domain:\n  content_root: knowledge\nindex:\n  by_tag: true\n  tag_labels:\n    cooking: 料理\n",
            encoding="utf-8",
        )
        (content / "vocabulary.yml").write_text(
            "types:\n  Note:\n    directory: notes\n    graph: false\ntags:\n  - cooking\n",
            encoding="utf-8",
        )
        (content / "notes" / "index.md").write_text("# Notes\n\n## エンティティ一覧\n\n", encoding="utf-8")
        (content / "notes" / "example.md").write_text(
            "---\ntype: Note\ntitle: Example\ndescription: D.\ntags: [cooking]\n"
            "timestamp: 2026-09-01T00:00:00Z\nsources: []\n---\n\nBody\n",
            encoding="utf-8",
        )
        index = content / "index.md"
        index.write_text("# Root\n", encoding="utf-8")
        return index

    def test_sync_check_reports_stale_tag_index_and_sync_writes_it(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            index = self._build(root)

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["sync", "--check", "--start", str(root), "--format", "json"])
            result = json.loads(output.getvalue())
            self.assertEqual(exit_code, 1)
            self.assertIn("knowledge/index.md", [d["path"] for d in result["diagnostics"]])
            self.assertEqual(index.read_text(encoding="utf-8"), "# Root\n")

            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["sync", "--start", str(root), "--format", "json"]), 0)
            text = index.read_text(encoding="utf-8")
            self.assertIn("### 料理（1件）\n\n- [Example](/notes/example.md) — Note\n", text)

            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["sync", "--check", "--start", str(root), "--format", "json"]), 0)

    def test_index_build_also_renders_tag_index(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            index = self._build(root)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["index", "build", "--start", str(root), "--format", "json"]), 0)
            self.assertIn("<!-- tag-index:start -->", index.read_text(encoding="utf-8"))


class ExtraChecksCliTest(unittest.TestCase):
    """validate.extra_checks は本体検証の後に repo_root で順に実行され、失敗は ERROR に集約される。"""

    def _build(self, root: Path, checks: str) -> None:
        content = root / "knowledge"
        content.mkdir()
        (root / "kb-domain.yml").write_text(
            f"domain:\n  content_root: knowledge\nvalidate:\n  extra_checks:\n{checks}",
            encoding="utf-8",
        )
        (content / "vocabulary.yml").write_text(
            "types:\n  Note:\n    directory: notes\n    graph: false\npredicates: {}\ntags: []\n",
            encoding="utf-8",
        )

    def test_failed_check_is_reported_as_error_with_json_detail(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            self._build(root, "    - test -f kb-domain.yml\n    - echo boom >&2; exit 3\n")
            output = io.StringIO()
            with redirect_stdout(output), redirect_stderr(io.StringIO()):
                exit_code = main(["validate", "--start", str(root), "--format", "json"])
            result = json.loads(output.getvalue())
            self.assertEqual(exit_code, 1)
            self.assertFalse(result["ok"])
            # cwd が repo_root なので相対パスの test -f が通る
            self.assertEqual(
                [(c["command"], c["returncode"], c["ok"]) for c in result["extra_checks"]],
                [("test -f kb-domain.yml", 0, True), ("echo boom >&2; exit 3", 3, False)],
            )
            failed = [d for d in result["diagnostics"] if d["code"] == "validation.extra_check.failed"]
            self.assertEqual(len(failed), 1)
            self.assertIn("exit 3", failed[0]["message"])
            self.assertIn("boom", failed[0]["message"])

    def test_all_checks_pass(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            self._build(root, "    - \"true\"\n")
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["validate", "--start", str(root), "--format", "json"])
            result = json.loads(output.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertTrue(result["ok"])
            self.assertEqual(result["diagnostics"], [])
            self.assertEqual(result["extra_checks"][0]["ok"], True)

    def test_doctor_warns_when_check_command_is_unavailable(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            self._build(root, "    - \"true\"\n    - no-such-command-xyz --check\n")
            (root / "knowledge" / "notes").mkdir()
            with redirect_stdout(io.StringIO()):
                main(["sync", "--start", str(root), "--format", "json"])
            output = io.StringIO()
            with redirect_stdout(output), redirect_stderr(io.StringIO()):
                exit_code = main(["doctor", "--start", str(root), "--format", "json"])
            result = json.loads(output.getvalue())
            unavailable = [d for d in result["diagnostics"] if d["code"] == "doctor.extra_check.unavailable"]
            self.assertEqual(len(unavailable), 1)
            self.assertEqual(unavailable[0]["severity"], "warning")
            self.assertIn("no-such-command-xyz", unavailable[0]["message"])
            # 警告のみなら doctor は成功扱い
            self.assertTrue(result["ok"])
            self.assertEqual(exit_code, 0)
