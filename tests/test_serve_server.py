"""配るルートと、配らないパスを確認する。"""

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import HTTPServer
from pathlib import Path

from kb_harness.project import Project
from kb_harness.serve.server import make_handler

DOMAIN = "domain:\n  kb_title: テスト知識ベース\n  content_root: knowledge\n"
VOCAB = "types:\n  Concept:\n    directory: concepts\npredicates: {}\ntags: [index]\n"
GRAPH = {
    "nodes": [
        {
            "path": "/concepts/example.md",
            "type": "Concept",
            "title": "例",
            "description": "説明。",
            "tags": ["index"],
        }
    ],
    "edges": [],
}


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "knowledge").mkdir()
        (self.root / "kb-domain.yml").write_text(DOMAIN, encoding="utf-8")
        (self.root / "knowledge" / "vocabulary.yml").write_text(VOCAB, encoding="utf-8")
        (self.root / "graph.json").write_text(
            json.dumps(GRAPH, ensure_ascii=False), encoding="utf-8"
        )
        self.project = Project.discover(self.root)
        self.server = HTTPServer(("127.0.0.1", 0), make_handler(self.project))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.conn = HTTPConnection("127.0.0.1", self.server.server_address[1])

    def tearDown(self):
        self.conn.close()
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def _get(self, path):
        self.conn.request("GET", path)
        res = self.conn.getresponse()
        return res.status, res.getheader("Content-Type") or "", res.read()

    def _rewrite_graph(self, graph):
        (self.root / "graph.json").write_text(
            json.dumps(graph, ensure_ascii=False), encoding="utf-8"
        )

    def _rewrite_title(self, title):
        (self.root / "kb-domain.yml").write_text(
            f'domain:\n  kb_title: "{title}"\n  content_root: knowledge\n',
            encoding="utf-8",
        )
        self.project = Project.discover(self.root)
        self.server.RequestHandlerClass = make_handler(self.project)

    def test_グラフ画面にデータが差し込まれて配られる(self):
        status, ctype, body = self._get("/")
        text = body.decode("utf-8")
        self.assertEqual(status, 200)
        self.assertTrue(ctype.startswith("text/html"))
        for marker in ("__KB_GRAPH__", "__KB_DESC__", "__KB_VIEWER__", "__KB_TITLE__"):
            self.assertNotIn(marker, text)
        self.assertIn("テスト知識ベース", text)
        self.assertIn("例", text)

    def test_apiのgraphがgraph_jsonをそのまま返す(self):
        status, ctype, body = self._get("/api/graph")
        self.assertEqual(status, 200)
        self.assertTrue(ctype.startswith("application/json"))
        self.assertEqual(json.loads(body), GRAPH)

    def test_列挙外のパスは配らない(self):
        for path in (
            "/support.js",
            "/vendor/react.production.min.js",
            "/vendor/../../serve.py",
            "/vendor/%2e%2e/%2e%2e/setup.py",
            "/vendor/..%2f..%2fsetup.py",
            "/vendor/./react.production.min.js",
            "/VENDOR/react.production.min.js",
            "/vendor/unknown.js",
            "/etc/passwd",
            "/app.js",
        ):
            status, _, _ = self._get(path)
            self.assertEqual(status, 404, path)

    def test_graph_jsonがなければ案内つきで404を返す(self):
        (self.root / "graph.json").unlink()
        status, _, body = self._get("/api/graph")
        self.assertEqual(status, 404)
        self.assertIn("kb sync", body.decode("utf-8"))

    def test_graph_jsonがなければグラフ画面も案内つきで404を返す(self):
        (self.root / "graph.json").unlink()
        status, _, body = self._get("/")
        self.assertEqual(status, 404)
        self.assertIn("kb sync", body.decode("utf-8"))

    def test_題名のhtmlがエスケープされる(self):
        self._rewrite_title("<script>alert(1)</script>")
        _, _, body = self._get("/")
        text = body.decode("utf-8")
        # 見出しの差し込み口は素のテキスト。タグとして解釈されてはならない
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", text)
        # JSON 側にも生の閉じタグが残ってはならない（script ブロックが閉じる）
        self.assertNotIn("</script>alert", text)
        self.assertNotIn("<script>alert(1)</script>", text)

    def test_説明文のscriptタグがブロックを閉じない(self):
        graph = json.loads(json.dumps(GRAPH))
        graph["nodes"][0]["description"] = "</script><img src=x onerror=alert(1)>"
        self._rewrite_graph(graph)
        _, _, body = self._get("/")
        text = body.decode("utf-8")
        self.assertNotIn("</script><img", text)
        self.assertIn("<\\/script>", text)

    def test_エンティティ題名がマーカー文字列でも差し込みが壊れない(self):
        graph = json.loads(json.dumps(GRAPH))
        graph["nodes"][0]["title"] = "__KB_DESC__"
        self._rewrite_graph(graph)
        _, _, body = self._get("/")
        text = body.decode("utf-8")
        # グラフに埋めた題名が、後続のマーカー置換で説明文の JSON に化けてはならない
        self.assertIn('"__KB_DESC__"', text)
        self.assertEqual(text.count("説明。"), 1)

    def test_同名ファイルが別ノードとして配られる(self):
        graph = {
            "nodes": [
                {"path": "/concepts/x.md", "type": "Concept", "title": "概念"},
                {"path": "/tools/x.md", "type": "Concept", "title": "道具"},
            ],
            "edges": [
                {
                    "source": "/concepts/x.md",
                    "predicate": "related-to",
                    "target": "/tools/x.md",
                }
            ],
        }
        self._rewrite_graph(graph)
        _, _, body = self._get("/")
        text = body.decode("utf-8")
        self.assertIn('"/concepts/x", "Concept", "概念"', text)
        self.assertIn('"/tools/x", "Concept", "道具"', text)
        self.assertIn('"/concepts/x", "related-to", "/tools/x"', text)


if __name__ == "__main__":
    unittest.main()
