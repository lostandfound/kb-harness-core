import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from kb_harness.entity import create_entity


class EntityActionTest(unittest.TestCase):
    def test_uses_injected_clock_for_reproducible_timestamp(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            (root / "vocabulary.yml").write_text(
                "types:\n  Concept:\n    directory: concepts\n"
                "predicates: {}\ntags: []\n",
                encoding="utf-8",
            )

            path = create_entity(
                root,
                "concept",
                "ontology",
                clock=lambda: datetime(2026, 9, 1, 1, 2, 3, tzinfo=timezone.utc),
            )

            self.assertIn(
                "timestamp: 2026-09-01T01:02:03Z",
                path.read_text(encoding="utf-8"),
            )

    def test_rejects_duplicate_without_overwriting_existing_entity(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            entity = root / "concepts" / "ontology.md"
            entity.parent.mkdir()
            entity.write_text("original", encoding="utf-8")
            (root / "vocabulary.yml").write_text(
                "types:\n  Concept:\n    directory: concepts\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "already exists"):
                create_entity(root, "concept", "ontology")

            self.assertEqual(entity.read_text(encoding="utf-8"), "original")


if __name__ == "__main__":
    unittest.main()
