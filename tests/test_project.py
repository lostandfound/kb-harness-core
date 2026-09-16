import tempfile
import unittest
from pathlib import Path

from kb_harness.project import Project, ProjectError


class ProjectTest(unittest.TestCase):
    def test_discovers_project_and_content_root_from_nested_path(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            content = root / "knowledge"
            nested = content / "people"
            nested.mkdir(parents=True)
            (root / "kb-domain.yml").write_text(
                "domain:\n  content_root: knowledge\n",
                encoding="utf-8",
            )

            project = Project.discover(nested)

            self.assertEqual(project.repo_root, root.resolve())
            self.assertEqual(project.content_root, content.resolve())

    def test_reports_malformed_domain_yaml_as_project_error(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            config = root / "kb-domain.yml"
            config.write_text("domain: [\n", encoding="utf-8")

            with self.assertRaisesRegex(ProjectError, "invalid YAML"):
                Project.from_config(config)


if __name__ == "__main__":
    unittest.main()


class ProjectIndexConfigTest(unittest.TestCase):
    def test_index_options_default_to_disabled(self):
        with tempfile.TemporaryDirectory() as tempdir:
            config = Path(tempdir) / "kb-domain.yml"
            config.write_text("domain:\n  content_root: knowledge\n", encoding="utf-8")
            project = Project.from_config(config)
            self.assertFalse(project.index_by_tag)
            self.assertEqual(project.tag_labels, {})

    def test_reads_index_by_tag_and_labels(self):
        with tempfile.TemporaryDirectory() as tempdir:
            config = Path(tempdir) / "kb-domain.yml"
            config.write_text(
                "domain:\n  content_root: knowledge\n"
                "index:\n  by_tag: true\n  tag_labels:\n    cooking: 料理\n",
                encoding="utf-8",
            )
            project = Project.from_config(config)
            self.assertTrue(project.index_by_tag)
            self.assertEqual(project.tag_labels, {"cooking": "料理"})
