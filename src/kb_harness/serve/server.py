"""知識グラフの閲覧画面をローカルに配る。

静的ファイルは列挙した名前だけを配る。パス操作でリポジトリ内の他のファイルを
読み出されないよう、ディレクトリ探索ではなく固定の対応表を使う。
"""

from __future__ import annotations

import html
import json
import re
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

from ..project import Project
from .viewer import build_viewer_config

MARKER = re.compile(r"__KB_(GRAPH|DESC|VIEWER|TITLE)__")
STATIC = Path(__file__).resolve().parent / "static"
VENDOR = {
    "react.production.min.js",
    "react-dom.production.min.js",
}


def _short(path: str) -> str:
    """グラフの識別子を、拡張子を落としたファイル名だけに詰める。"""
    return path.rsplit("/", 1)[-1].removesuffix(".md")


def _dump(value: object) -> str:
    """JSON にして script ブロックの中へ置ける形にする。

    `</` を `<\\/` へ写す。JSON 文字列中では `\\/` は `/` と等価で値は変わらないが、
    これをしないと description や題名に含まれる `</script>` が script を閉じ、
    以降の JS を殺して任意の HTML を注入できてしまう。
    """
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def _page(project: Project) -> bytes:
    """テンプレートにグラフ・説明文・表示情報を差し込む。"""
    graph = json.loads((project.repo_root / "graph.json").read_text(encoding="utf-8"))
    nodes = [
        [_short(n["path"]), n["type"], n["title"], "|".join(n.get("tags") or [])]
        for n in graph.get("nodes", [])
    ]
    edges = [
        [_short(e["source"]), e["predicate"], _short(e["target"])]
        for e in graph.get("edges", [])
    ]
    descriptions = {
        _short(n["path"]): n.get("description", "") for n in graph.get("nodes", [])
    }
    viewer = build_viewer_config(project)
    table = {
        "GRAPH": _dump({"nodes": nodes, "edges": edges}),
        "DESC": _dump(descriptions),
        "VIEWER": _dump(viewer),
        # 題名は dc が描き直す領域の中にあるため、JS ではなく静的に埋める
        "TITLE": html.escape(viewer["title"]),
    }
    template = (STATIC / "graph.html").read_text(encoding="utf-8")
    # 置換を 1 度だけ走らせる。replace を連ねると、先に埋めた値の中に次のマーカー
    # 文字列が含まれていたとき、そこまで置換されてページが壊れる。
    return MARKER.sub(lambda m: table[m.group(1)], template).encode("utf-8")


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
