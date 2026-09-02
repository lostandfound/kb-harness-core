import tempfile
import unittest
from pathlib import Path

from kb_harness.graph import plan_graph


class GraphTest(unittest.TestCase):
    def test_plan_graph_reports_change_without_writing(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            people = root / "people"
            people.mkdir()
            (root / "vocabulary.yml").write_text(
                "types:\n  Person:\n    directory: people\n"
                "predicates: {}\ntags: [history]\n",
                encoding="utf-8",
            )
            (people / "example.md").write_text(
                "---\ntype: Person\ntitle: Example\ndescription: Description.\n"
                "tags: [history]\ntimestamp: 2026-09-01T00:00:00Z\n"
                "sources: [Test]\n---\n\nBody\n",
                encoding="utf-8",
            )
            output = root.parent / "graph.json"
            output.write_text("{}\n", encoding="utf-8")

            changes = plan_graph(root, output)

            self.assertEqual(output.read_text(encoding="utf-8"), "{}\n")
            self.assertEqual(list(changes), [output.resolve()])
            self.assertIn('"path": "/people/example.md"', changes[output.resolve()])


if __name__ == "__main__":
    unittest.main()
