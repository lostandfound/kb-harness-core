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

    def test_テンプレートが4つの差し込み口を持つ(self):
        text = (STATIC / "graph.html").read_text(encoding="utf-8")
        for marker in ("__KB_GRAPH__", "__KB_DESC__", "__KB_VIEWER__", "__KB_TITLE__"):
            self.assertIn(marker, text, marker)

    def test_テンプレートが書体以外のCDNを参照しない(self):
        # 描画に要るものは同梱する。書体だけは例外で、届かなければ
        # システムフォントに落ちるだけなので外部から読む。
        # src= だけでなく href= も見る。書体の読み込みが素通りしていたため。
        # unpkg の URL は window.__resources の写像キーとして残るので、属性の形で検査する。
        text = (STATIC / "graph.html").read_text(encoding="utf-8")
        for host in ("unpkg.com", "cdn.jsdelivr.net", "cdnjs.cloudflare.com"):
            for attr in ("src", "href"):
                self.assertNotIn(f'{attr}="https://{host}', text, f"{attr} {host}")

    def test_書体だけは外部から読む(self):
        # 同梱せず外部に置いた判断を、意図として検査に残す
        text = (STATIC / "graph.html").read_text(encoding="utf-8")
        self.assertIn('href="https://fonts.googleapis.com/css2', text)

    def test_ランタイムが期待するReactを同梱している(self):
        # support.js は unpkg の React を SRI つきで読む。同梱物が同じものであること。
        runtime = (STATIC / "support.js").read_text(encoding="utf-8")
        for const, name in (
            ("REACT_SRI", "react.production.min.js"),
            ("REACT_DOM_SRI", "react-dom.production.min.js"),
        ):
            found = re.search(rf'{const} = "sha384-([^"]+)"', runtime)
            self.assertIsNotNone(found, const)
            expected = found.group(1)
            digest = hashlib.sha384((STATIC / "vendor" / name).read_bytes()).digest()
            self.assertEqual(base64.b64encode(digest).decode(), expected, name)


if __name__ == "__main__":
    unittest.main()
