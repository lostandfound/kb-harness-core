"""vocabulary.yml と kb-domain.yml から、ビューアの表示情報を導けることを確認する。"""

import tempfile
import unittest
from pathlib import Path

from kb_harness.project import Project, ProjectError
from kb_harness.serve.viewer import PALETTE, build_viewer_config

DOMAIN = """domain:
  kb_title: テスト知識ベース
  content_root: knowledge
"""

VOCAB = """types:
  Course:
    directory: courses
  Concept:
    directory: concepts
predicates:
  teaches:
    description: コースが扱う学習項目
  related-to:
    domain: [Concept]
    range: [Concept]
tags: [index]
"""


class ViewerConfigTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "knowledge").mkdir()
        (self.root / "kb-domain.yml").write_text(DOMAIN, encoding="utf-8")
        (self.root / "knowledge" / "vocabulary.yml").write_text(VOCAB, encoding="utf-8")
        self.project = Project.discover(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_型はvocabularyの定義順で色を受け取る(self):
        config = build_viewer_config(self.project)
        self.assertEqual(
            config["types"],
            [
                {"name": "Course", "color": PALETTE[0]},
                {"name": "Concept", "color": PALETTE[1]},
            ],
        )

    def test_型を末尾に足しても既存の色は動かない(self):
        before = build_viewer_config(self.project)["types"]
        path = self.root / "knowledge" / "vocabulary.yml"
        path.write_text(
            VOCAB.replace("predicates:", "  Tool:\n    directory: tools\npredicates:"),
            encoding="utf-8",
        )
        after = build_viewer_config(Project.discover(self.root))["types"]
        self.assertEqual(after[:2], before)
        self.assertEqual(after[2], {"name": "Tool", "color": PALETTE[2]})

    def test_述語の表示名はdescriptionから入る(self):
        config = build_viewer_config(self.project)
        self.assertIn({"name": "teaches", "label": "コースが扱う学習項目"}, config["predicates"])

    def test_descriptionのない述語は名前のまま出る(self):
        config = build_viewer_config(self.project)
        self.assertIn({"name": "related-to", "label": "related-to"}, config["predicates"])

    def test_題名はkb_titleから入る(self):
        self.assertEqual(build_viewer_config(self.project)["title"], "テスト知識ベース")

    def test_kb_titleがなければドメイン名にする(self):
        (self.root / "kb-domain.yml").write_text(
            "domain:\n  name: フォールバック\n  content_root: knowledge\n", encoding="utf-8"
        )
        config = build_viewer_config(Project.discover(self.root))
        self.assertEqual(config["title"], "フォールバック")

    def _types(self, count):
        many = "types:\n" + "".join(
            f"  T{i}:\n    directory: d{i}\n" for i in range(count)
        ) + "predicates: {}\ntags: [index]\n"
        (self.root / "knowledge" / "vocabulary.yml").write_text(many, encoding="utf-8")
        return build_viewer_config(Project.discover(self.root))["types"]

    def test_パレットを超える型にも他と重ならない色が付く(self):
        types = self._types(len(PALETTE) * 3)
        colors = [t["color"] for t in types]
        self.assertEqual(colors[: len(PALETTE)], list(PALETTE))
        self.assertEqual(len(set(c.lower() for c in colors)), len(colors))
        for color in colors:
            self.assertRegex(color, r"^#[0-9a-f]{6}$")

    def test_パレットを超えて付けた色も型を足して動かない(self):
        before = [t["color"] for t in self._types(len(PALETTE) + 3)]
        after = [t["color"] for t in self._types(len(PALETTE) + 6)]
        self.assertEqual(after[: len(before)], before)

    def test_typesがリストでも型なしとして扱う(self):
        (self.root / "knowledge" / "vocabulary.yml").write_text(
            "types:\n  - Course\npredicates: {}\ntags: [index]\n", encoding="utf-8"
        )
        self.assertEqual(build_viewer_config(Project.discover(self.root))["types"], [])

    def test_predicatesがリストでも述語なしとして扱う(self):
        (self.root / "knowledge" / "vocabulary.yml").write_text(
            "types: {}\npredicates:\n  - teaches\ntags: [index]\n", encoding="utf-8"
        )
        config = build_viewer_config(Project.discover(self.root))
        self.assertEqual(config["predicates"], [])

    def test_vocabularyの最上位がリストでも空の定義として扱う(self):
        (self.root / "knowledge" / "vocabulary.yml").write_text(
            "- Course\n- Concept\n", encoding="utf-8"
        )
        config = build_viewer_config(Project.discover(self.root))
        self.assertEqual(config["types"], [])
        self.assertEqual(config["predicates"], [])
        self.assertEqual(config["title"], "テスト知識ベース")

    def test_vocabularyが壊れていればProjectErrorになる(self):
        (self.root / "knowledge" / "vocabulary.yml").write_text(
            "types:\n  Course: [\n", encoding="utf-8"
        )
        with self.assertRaises(ProjectError) as caught:
            build_viewer_config(Project.discover(self.root))
        self.assertIn("invalid YAML", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
