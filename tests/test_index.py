import tempfile
import unittest
from pathlib import Path

from kb_harness.index import plan_index


class IndexTest(unittest.TestCase):
    def test_plan_index_reports_change_without_writing(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            notes = root / "notes"
            notes.mkdir()
            (root / "vocabulary.yml").write_text(
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

            changes = plan_index(root)

            self.assertEqual(index.read_text(encoding="utf-8"), original)
            self.assertEqual(list(changes), [index.resolve()])
            self.assertIn(
                "- [Example](/notes/example.md) — Description.",
                changes[index.resolve()],
            )


if __name__ == "__main__":
    unittest.main()
