"""同梱するビューアが差し込み口を持ち、外部資産に依存しないことを確認する。"""

import unittest
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "src" / "kb_harness" / "serve" / "static"


class AssetTest(unittest.TestCase):
    def test_必要なファイルが揃っている(self):
        for name in (
            "graph.html",
            "flashcards.html",
            "flashcards.css",
            "flashcards.js",
            "README.md",
            "vendor/graphology.umd.min.js",
            "vendor/sigma.min.js",
            "vendor/GRAPHOLOGY-LICENSE.txt",
            "vendor/SIGMA-LICENSE.txt",
        ):
            self.assertTrue((STATIC / name).is_file(), name)

    def test_テンプレートが4つの差し込み口を持つ(self):
        text = (STATIC / "graph.html").read_text(encoding="utf-8")
        for marker in ("__KB_GRAPH__", "__KB_DESC__", "__KB_VIEWER__", "__KB_TITLE__"):
            self.assertIn(marker, text, marker)

    def test_学習カード画面が全KB共通のAPIと言語判定を使う(self):
        text = (STATIC / "flashcards.js").read_text(encoding="utf-8")
        self.assertIn('fetch("/api/flashcards")', text)
        self.assertIn("navigator.languages", text)
        self.assertIn('startsWith("ja")', text)
        self.assertNotIn("kanagata", text)

    def test_テンプレートが外部資産を参照しない(self):
        text = (STATIC / "graph.html").read_text(encoding="utf-8")
        for marker in ("unpkg.com", "cdn.jsdelivr.net", "cdnjs.cloudflare.com", "fonts.googleapis.com"):
            self.assertNotIn(marker, text, marker)


if __name__ == "__main__":
    unittest.main()
