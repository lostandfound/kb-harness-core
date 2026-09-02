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
                {"changed": [], "diagnostics": [], "ok": True},
            )

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
            self.assertEqual(result["diagnostics"], [])
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
            self.assertEqual(result["diagnostics"][0]["code"], "doctor.generated_stale")


if __name__ == "__main__":
    unittest.main()
