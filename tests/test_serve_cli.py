"""kb serve の引数が serve() へそのまま渡ることを確認する。"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kb_harness.cli import main

DOMAIN = "domain:\n  kb_title: テスト知識ベース\n  content_root: knowledge\n"
VOCAB = "types: {}\npredicates: {}\ntags: [index]\n"


class ServeCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "knowledge").mkdir()
        (self.root / "kb-domain.yml").write_text(DOMAIN, encoding="utf-8")
        (self.root / "knowledge" / "vocabulary.yml").write_text(VOCAB, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_既定ではポート8000でブラウザを開かない(self):
        with patch("kb_harness.cli.serve") as spy:
            code = main(["serve", "--start", str(self.root)])
        self.assertEqual(code, 0)
        _, kwargs = spy.call_args
        self.assertEqual(kwargs["port"], 8000)
        self.assertFalse(kwargs["open_browser"])

    def test_portとopenが渡る(self):
        with patch("kb_harness.cli.serve") as spy:
            main(["serve", "--start", str(self.root), "--port", "8123", "--open"])
        _, kwargs = spy.call_args
        self.assertEqual(kwargs["port"], 8123)
        self.assertTrue(kwargs["open_browser"])

    def test_知識ベースの外では案内して終わる(self):
        with tempfile.TemporaryDirectory() as empty:
            code = main(["serve", "--start", empty])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
