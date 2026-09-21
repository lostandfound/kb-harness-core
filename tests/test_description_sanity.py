"""description の内容の検査を確認する。

必須フィールドの有無だけでは、改版で前の版の断片が残った description が
そのまま通る。検索結果と index に重複した文が出続けるため、内容を検査する。
"""

import tempfile
import unittest
from pathlib import Path

from kb_harness.validation import validate

VOCAB = (
    "types:\n"
    "  Note:\n"
    "    directory: notes\n"
    "    sources_required: false\n"
    "predicates: {}\n"
    "tags: [index, misc]\n"
)
INDEX = (
    "---\ntype: Index\ntitle: notes\ndescription: 一覧。\n"
    "tags: [index]\ntimestamp: 2026-09-01T00:00:00Z\n---\n\n# notes\n\n## エンティティ一覧\n\n"
)


def _entity(description: str, title: str = "スキル") -> str:
    return (
        f"---\ntype: Note\ntitle: {title}\ndescription: {description}\n"
        "tags: [misc]\ntimestamp: 2026-09-01T00:00:00Z\n---\n\n# 例\n\n## 概要\n\n本文。\n"
    )


class DescriptionSanityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.content = Path(self.tmp.name) / "knowledge"
        (self.content / "notes").mkdir(parents=True)
        (self.content / "notes" / "index.md").write_text(INDEX, encoding="utf-8")
        (Path(self.tmp.name) / "kb-domain.yml").write_text(
            "domain:\n  content_root: knowledge\n", encoding="utf-8"
        )
        (self.content / "vocabulary.yml").write_text(VOCAB, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, description: str, title: str = "スキル") -> None:
        (self.content / "notes" / "memo.md").write_text(
            _entity(description, title), encoding="utf-8"
        )

    def test_通常の説明は通る(self):
        self._write("SKILL.md の description をきっかけに読み込まれる指示の集合。")
        self.assertEqual([e for e in validate(self.content) if "description" in e], [])

    def test_同じ文が繰り返されていると落ちる(self):
        # 改版で前の版の末尾が消し切れず二重になった状態
        self._write("必要時にだけ読み込まれる指示の集合。必要時にだけ読み込まれる指示の集合。")
        errors = validate(self.content)
        self.assertTrue(any("同じ記述が繰り返されている" in e for e in errors), errors)

    def test_空の説明は落ちる(self):
        self._write('"   "')
        errors = validate(self.content)
        self.assertTrue(any("description が空である" in e for e in errors), errors)

    def test_短い語の重複では落ちない(self):
        # 「スキル。」のような短い語の反復は文体上ありうるので誤検出しない
        self._write("スキル。スキル。実体は SKILL.md である。")
        self.assertEqual([e for e in validate(self.content) if "description" in e], [])

    def test_語尾が同じだけでは落ちない(self):
        self._write("これは概念である。あれも概念である。")
        self.assertEqual([e for e in validate(self.content) if "description" in e], [])

    def test_前の版の断片が残っていると落ちる(self):
        # 完全一致ではなく、末尾だけが重なる形の消し残り
        self._write("必要時にだけ自動で読み込まれる指示・スクリプト・リソースの集合。 な指示・スクリプト・リソースの集合。")
        errors = validate(self.content)
        self.assertTrue(any("同じ記述が繰り返されている" in e for e in errors), errors)

    def test_titleと同一なら警告に出る(self):
        self._write("スキル", title="スキル")
        warnings: list[str] = []
        errors = validate(self.content, warnings)
        self.assertEqual([e for e in errors if "description" in e], [])
        self.assertTrue(any("title と同一" in w for w in warnings), warnings)

    def test_長すぎる説明は警告に出る(self):
        self._write("あ" * 241 + "。")
        warnings: list[str] = []
        errors = validate(self.content, warnings)
        self.assertEqual([e for e in errors if "description" in e], [])
        self.assertTrue(any("description が長い" in w for w in warnings), warnings)


if __name__ == "__main__":
    unittest.main()
