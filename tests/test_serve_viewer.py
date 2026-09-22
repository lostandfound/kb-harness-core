"""vocabulary.yml と kb-domain.yml から、ビューアの表示情報を導けることを確認する。"""

import tempfile
import unittest
from pathlib import Path

from kb_harness.project import Project
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

    def test_型が多くてもパレットを循環して色が付く(self):
        many = "types:\n" + "".join(
            f"  T{i}:\n    directory: d{i}\n" for i in range(len(PALETTE) + 2)
        ) + "predicates: {}\ntags: [index]\n"
        (self.root / "knowledge" / "vocabulary.yml").write_text(many, encoding="utf-8")
        types = build_viewer_config(Project.discover(self.root))["types"]
        self.assertEqual(len(types), len(PALETTE) + 2)
        self.assertEqual(types[len(PALETTE)]["color"], PALETTE[0])


if __name__ == "__main__":
    unittest.main()
