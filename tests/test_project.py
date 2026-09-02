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
