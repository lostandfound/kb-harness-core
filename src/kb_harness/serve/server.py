"""知識グラフの閲覧画面をローカルに配る。

静的ファイルは列挙した名前だけを配る。パス操作でリポジトリ内の他のファイルを
読み出されないよう、ディレクトリ探索ではなく固定の対応表を使う。
"""

from __future__ import annotations

import html
import json
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

from ..project import Project
from .viewer import build_viewer_config

STATIC = Path(__file__).resolve().parent / "static"
VENDOR = {
    "react.production.min.js",
    "react-dom.production.min.js",
}


def _page(project: Project) -> bytes:
    """テンプレートにグラフ・説明文・表示情報を差し込む。"""
    graph = json.loads((project.repo_root / "graph.json").read_text(encoding="utf-8"))
    short = lambda p: p.rsplit("/", 1)[-1].removesuffix(".md")  # noqa: E731
    nodes = [
        [short(n["path"]), n["type"], n["title"], "|".join(n.get("tags") or [])]
        for n in graph.get("nodes", [])
    ]
    edges = [
        [short(e["source"]), e["predicate"], short(e["target"])]
        for e in graph.get("edges", [])
    ]
    descriptions = {
        short(n["path"]): n.get("description", "") for n in graph.get("nodes", [])
    }
    dump = lambda value: json.dumps(value, ensure_ascii=False)  # noqa: E731
    viewer = build_viewer_config(project)
    return (
        (STATIC / "graph.html")
        .read_text(encoding="utf-8")
        .replace("__KB_GRAPH__", dump({"nodes": nodes, "edges": edges}))
        .replace("__KB_DESC__", dump(descriptions))
        .replace("__KB_VIEWER__", dump(viewer))
        # 題名は dc が描き直す領域の中にあるため、JS ではなく静的に埋める
        .replace("__KB_TITLE__", html.escape(viewer["title"]))
        .encode("utf-8")
    )


def make_handler(project: Project) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 （BaseHTTPRequestHandler の命名規約）
            path = urlparse(self.path).path
            graph_json = project.repo_root / "graph.json"

            if path == "/":
                if not graph_json.is_file():
                    self._send_text(
                        404, "graph.json がない。kb sync を実行してから開く。"
                    )
                    return
                self._send(_page(project), "text/html; charset=utf-8")
                return

            if path == "/api/graph":
                if not graph_json.is_file():
                    self._send_text(
                        404, "graph.json がない。kb sync を実行してから開く。"
                    )
                    return
                self._send(graph_json.read_bytes(), "application/json; charset=utf-8")
                return

            if path == "/support.js":
                self._send(
                    (STATIC / "support.js").read_bytes(),
                    "text/javascript; charset=utf-8",
                )
                return

            if path.startswith("/vendor/"):
                name = path.removeprefix("/vendor/")
                if name in VENDOR:
                    self._send(
                        (STATIC / "vendor" / name).read_bytes(),
                        "text/javascript; charset=utf-8",
                    )
                    return

            self.send_error(404)

        def log_message(self, *args) -> None:
            """既定の標準エラーへのアクセスログを止める。"""

        def _send(self, body: bytes, content_type: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_text(self, status: int, message: str) -> None:
            body = message.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def serve(project: Project, port: int = 8000, open_browser: bool = False) -> None:
    """127.0.0.1 でだけ待ち受ける。外部へ公開しない。"""
    server = HTTPServer(("127.0.0.1", port), make_handler(project))
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"kb serve: {url}")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
