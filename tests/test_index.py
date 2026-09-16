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


class TagIndexTest(unittest.TestCase):
    """タグ別一覧はルート index.md のマーカー区間だけを管理し、区間外は保持する。"""

    def _build_kb(self, root: Path) -> Path:
        (root / "vocabulary.yml").write_text(
            "types:\n  Note:\n    directory: notes\n    graph: false\n"
            "  Dish:\n    directory: dishes\n    graph: false\n"
            "tags:\n  - cooking\n  - science\n  - unused\n",
            encoding="utf-8",
        )
        for directory, name, type_name, tags in (
            ("notes", "b-note", "Note", "[science, cooking]"),
            ("dishes", "a-dish", "Dish", "[cooking]"),
        ):
            (root / directory).mkdir()
            (root / directory / f"{name}.md").write_text(
                f"---\ntype: {type_name}\ntitle: {name.upper()}\ndescription: D.\n"
                f"tags: {tags}\ntimestamp: 2026-09-01T00:00:00Z\nsources: []\n---\n\nBody\n",
                encoding="utf-8",
            )
        index = root / "index.md"
        index.write_text("# Root\n\n手書きの本文\n", encoding="utf-8")
        return index

    def test_disabled_by_default_leaves_root_index_untouched(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            self._build_kb(root)
            self.assertEqual(plan_index(root), {})

    def test_appends_marker_section_when_missing(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            index = self._build_kb(root)

            changes = plan_index(root, by_tag=True, tag_labels={"cooking": "料理"})

            rendered = changes[index.resolve()]
            self.assertTrue(rendered.startswith("# Root\n\n手書きの本文\n\n<!-- tag-index:start -->\n"))
            self.assertTrue(rendered.endswith("<!-- tag-index:end -->\n"))
            # vocabulary.yml の tags 順、ラベル未指定はタグ ID のまま、該当なしのタグは省く
            self.assertIn("### 料理（2件）\n\n- [A-DISH](/dishes/a-dish.md) — Dish\n- [B-NOTE](/notes/b-note.md) — Note\n", rendered)
            self.assertIn("### science（1件）\n\n- [B-NOTE](/notes/b-note.md) — Note\n", rendered)
            self.assertNotIn("unused", rendered)
            self.assertLess(rendered.index("### 料理"), rendered.index("### science"))

    def test_replaces_existing_section_and_keeps_surroundings(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            index = self._build_kb(root)
            index.write_text(
                "# Root\n\n<!-- tag-index:start -->\nold\n<!-- tag-index:end -->\n\n## 後書き\n",
                encoding="utf-8",
            )

            changes = plan_index(root, by_tag=True)

            rendered = changes[index.resolve()]
            self.assertNotIn("old", rendered)
            self.assertTrue(rendered.endswith("<!-- tag-index:end -->\n\n## 後書き\n"))
            self.assertIn("### cooking（2件）", rendered)

    def test_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            index = self._build_kb(root)
            first = plan_index(root, by_tag=True)[index.resolve()]
            index.write_text(first, encoding="utf-8")
            self.assertEqual(plan_index(root, by_tag=True), {})
