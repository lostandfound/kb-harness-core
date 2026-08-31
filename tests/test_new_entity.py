import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from new_entity import new_entity


class NewEntityTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        (self.root / "vocabulary.yml").write_text(
            """types:
  Concept:
    directory: concepts
  Product:
    directory: products
    sections: [概要, 主な機能, 関連項目]
predicates: {}
tags: []
""",
            encoding="utf-8",
        )

    def tearDown(self):
        self.tempdir.cleanup()

    def test_generates_domain_specific_type_with_default_sections(self):
        path = new_entity(self.root, "concept", "ontology")

        text = path.read_text(encoding="utf-8")
        self.assertIn("type: Concept", text)
        self.assertIn("## 概要", text)
        self.assertIn("## 詳細", text)
        self.assertIn("## 関連項目", text)

    def test_uses_sections_from_vocabulary(self):
        path = new_entity(self.root, "product", "foundry")

        text = path.read_text(encoding="utf-8")
        self.assertIn("## 主な機能", text)

    def test_rejects_unknown_type_without_creating_a_file(self):
        with self.assertRaisesRegex(ValueError, "unknown type"):
            new_entity(self.root, "person", "example")

        self.assertFalse((self.root / "people" / "example.md").exists())


if __name__ == "__main__":
    unittest.main()
