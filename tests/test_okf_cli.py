import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from kb_harness.cli import main
from kb_harness.okf import OkfExportError


class OkfCliTest(unittest.TestCase):
    def _kb(self):
        tempdir = tempfile.TemporaryDirectory()
        root = Path(tempdir.name)
        content = root / "knowledge"
        content.mkdir()
        (root / "kb-domain.yml").write_text("domain:\n  content_root: knowledge\n", encoding="utf-8")
        (content / "vocabulary.yml").write_text("types: {}\n", encoding="utf-8")
        (content / "note.md").write_text("---\ntype: Note\n---\n\nBody\n", encoding="utf-8")
        return tempdir, root

    def test_export_okf_dry_run_is_write_free(self):
        # Given a minimal KB and an output path
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            content = root / "knowledge"
            content.mkdir()
            (root / "kb-domain.yml").write_text("domain:\n  content_root: knowledge\n", encoding="utf-8")
            (content / "vocabulary.yml").write_text("types: {}\n", encoding="utf-8")
            (content / "note.md").write_text("---\ntype: Note\n---\n\nBody\n", encoding="utf-8")
            output = root / "export"
            stdout = io.StringIO()

            # When exporting in dry-run mode
            with redirect_stdout(stdout):
                exit_code = main(["export", "okf", "--start", str(root), "--output", str(output), "--format", "json", "--dry-run"])

            # Then the plan succeeds without creating files
            self.assertEqual(exit_code, 0)
            result = json.loads(stdout.getvalue())
            self.assertTrue(result["ok"])
            self.assertTrue(result["dry_run"])
            self.assertFalse(output.exists())

    def test_export_okf_writes_bundle(self):
        # Given a valid KB and a nonexistent destination
        tempdir, root = self._kb()
        with tempdir:
            output = root / "export"
            # When exporting normally
            exit_code = main(["export", "okf", "--start", str(root), "--output", str(output), "--format", "json"])
            # Then the bundle is written
            self.assertEqual(exit_code, 0)
            self.assertTrue((output / "note.md").is_file())

    def test_export_okf_json_changed_is_sorted(self):
        # Given a valid KB
        tempdir, root = self._kb()
        with tempdir:
            output = root / "export"
            stdout = io.StringIO()
            # When exporting as JSON
            with redirect_stdout(stdout):
                exit_code = main(["export", "okf", "--start", str(root), "--output", str(output), "--format", "json", "--dry-run"])
            # Then changed paths are deterministic and relative
            result = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(result["changed"], sorted(result["changed"]))
            self.assertTrue(all(not Path(path).is_absolute() for path in result["changed"]))

    def test_export_okf_allows_empty_existing_directory(self):
        # Given an existing empty destination
        tempdir, root = self._kb()
        with tempdir:
            output = root / "export"
            output.mkdir()
            # When exporting
            exit_code = main(["export", "okf", "--start", str(root), "--output", str(output)])
            # Then it succeeds
            self.assertEqual(exit_code, 0)

    def _error_code(self, root, output, *extra):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(["export", "okf", "--start", str(root), "--output", str(output), "--format", "json", *extra])
        return code, json.loads(stdout.getvalue() or stderr.getvalue())

    def test_export_okf_rejects_same_repo_and_content_roots(self):
        # Given a KB
        tempdir, root = self._kb()
        with tempdir:
            # When destination is a protected root
            for output in (root, root / "knowledge"):
                code, result = self._error_code(root, output)
                # Then a namespaced argument error is returned
                self.assertEqual(code, 2)
                self.assertTrue(result["diagnostics"][0]["code"].startswith("okf.output."))

    def test_export_okf_rejects_existing_file_and_nonempty_directory(self):
        # Given a KB and occupied destinations
        tempdir, root = self._kb()
        with tempdir:
            file = root / "file"
            file.write_text("x", encoding="utf-8")
            directory = root / "directory"
            directory.mkdir()
            (directory / "x").write_text("x", encoding="utf-8")
            # When exporting to either destination
            for output in (file, directory):
                code, result = self._error_code(root, output)
                # Then it is rejected
                self.assertEqual(code, 2)
                self.assertTrue(result["diagnostics"][0]["code"].startswith("okf.output."))

    def test_export_okf_rejects_symlink_into_content(self):
        # Given a symlinked destination path resolving into content
        tempdir, root = self._kb()
        with tempdir:
            link = root / "inside"
            link.symlink_to(root / "knowledge", target_is_directory=True)
            # When exporting through the symlink
            code, result = self._error_code(root, link / "bundle")
            # Then containment protection applies
            self.assertEqual(code, 2)
            self.assertTrue(result["diagnostics"][0]["code"].startswith("okf.output."))

    def test_export_okf_planner_error_is_domain_failure(self):
        # Given a planner that reports invalid source data
        tempdir, root = self._kb()
        with tempdir, patch("kb_harness.cli.plan_okf_export", side_effect=OkfExportError("okf.source.invalid", "bad source")):
            # When exporting
            code, result = self._error_code(root, root / "export")
            # Then the domain error has exit status one
            self.assertEqual(code, 1)
            self.assertEqual(result["diagnostics"][0]["code"], "okf.source.invalid")

    def test_export_okf_apply_failure_is_internal_error(self):
        # Given a valid plan but a failed atomic apply
        tempdir, root = self._kb()
        with tempdir, patch("kb_harness.cli.apply_changes_atomically", side_effect=OSError("boom")):
            # When exporting normally
            code, result = self._error_code(root, root / "export")
            # Then no success is reported and the destination remains absent
            self.assertEqual(code, 3)
            self.assertEqual(result["diagnostics"][0]["code"], "internal.error")
            self.assertFalse((root / "export").exists())


if __name__ == "__main__":
    unittest.main()
