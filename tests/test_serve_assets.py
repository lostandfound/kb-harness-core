"""同梱した静的資産が、差し込み口を持ち外部を参照しないことを確認する。"""

import base64
import hashlib
import re
import unittest
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "src" / "kb_harness" / "serve" / "static"


class AssetTest(unittest.TestCase):
    def test_必要なファイルが揃っている(self):
        for name in (
            "graph.html",
            "support.js",
            "README.md",
            "vendor/react.production.min.js",
            "vendor/react-dom.production.min.js",
        ):
            self.assertTrue((STATIC / name).is_file(), name)

    def test_テンプレートが3つの差し込み口を持つ(self):
        text = (STATIC / "graph.html").read_text(encoding="utf-8")
        for marker in ("__KB_GRAPH__", "__KB_DESC__", "__KB_VIEWER__"):
            self.assertIn(marker, text, marker)

    def test_テンプレートがCDNを参照しない(self):
        text = (STATIC / "graph.html").read_text(encoding="utf-8")
        for host in ("unpkg.com", "cdn.jsdelivr.net", "cdnjs.cloudflare.com"):
            self.assertNotIn(f'src="https://{host}', text, host)

    def test_ランタイムが期待するReactを同梱している(self):
        # support.js は unpkg の React を SRI つきで読む。同梱物が同じものであること。
        runtime = (STATIC / "support.js").read_text(encoding="utf-8")
        for const, name in (
            ("REACT_SRI", "react.production.min.js"),
            ("REACT_DOM_SRI", "react-dom.production.min.js"),
        ):
            expected = re.search(rf'{const} = "sha384-([^"]+)"', runtime).group(1)
            digest = hashlib.sha384((STATIC / "vendor" / name).read_bytes()).digest()
            self.assertEqual(base64.b64encode(digest).decode(), expected, name)


if __name__ == "__main__":
    unittest.main()
