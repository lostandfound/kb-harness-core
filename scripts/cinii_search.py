#!/usr/bin/env python3
"""CiNii Research OpenSearch API で論文を検索し、references.yml 登録用の YAML を出力する。

使い方:
  CINII_APP_ID=<your-app-id> python3 scripts/cinii_search.py "<ドメインのキーワード>" [--count 5]

アプリケーション ID は環境変数 CINII_APP_ID で渡す（リポジトリには記録しない）。
リポジトリ直下に .env があれば KEY=VALUE 形式として読み込む（.env は gitignore 済み）。
"""
import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://cir.nii.ac.jp/opensearch/articles"


def load_dotenv() -> None:
    env = Path(__file__).resolve().parent.parent / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def slugify(author: str, year: str, url: str = "") -> str:
    # 日本語著者名は決定論的にローマ字化できないため、ASCII 化で空になる場合は
    # CRID 末尾を仮 ID に使う（いずれもユーザー編集前提）
    base = re.sub(r"[^a-z0-9]+", "-", author.lower()).strip("-")
    if not base:
        crid = re.search(r"crid/(\d+)", url)
        base = f"crid{crid.group(1)[-6:]}" if crid else "ref"
    return f"{base}-{year}" if year else base


def search(query: str, count: int, app_id: str) -> list[dict]:
    params = urllib.parse.urlencode(
        {"q": query, "count": count, "format": "json", "appid": app_id}
    )
    req = urllib.request.Request(
        f"{API}?{params}",
        headers={"User-Agent": "kb-harness-cinii/1.0"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.load(resp)
    items = data.get("items") or []
    results = []
    for it in items:
        title = it.get("title", "")
        authors = it.get("dc:creator") or []
        if isinstance(authors, str):
            authors = [authors]
        pub = it.get("prism:publicationName", "")
        year = str(it.get("prism:publicationDate", ""))[:4]
        link = it.get("@id") or it.get("link", {}).get("@id", "")
        results.append(
            {"title": title, "authors": authors, "venue": pub, "year": year, "url": link}
        )
    return results


def render_results(results: list[dict], output_format: str = "yaml") -> str:
    """Render search results; JSON is directly consumable by ``reference spec``."""
    if output_format == "json":
        items = [{**r, "type": "journal-article"} for r in results]
        return json.dumps({"results": items}, ensure_ascii=False, indent=2) + "\n"
    lines = []
    for r in results:
        author = "、".join(r["authors"]) if r["authors"] else "不明"
        ref_id = slugify(r["authors"][0] if r["authors"] else "ref", r["year"], r["url"])
        lines.extend([f"# --- references.yml 登録案（ID は要編集: {ref_id}） ---", f"{ref_id}:", "  type: journal-article", f"  author: {author}", f"  title: {r['title']}"])
        if r["venue"]: lines.append(f"  venue: {r['venue']}")
        if r["year"]: lines.append(f"  year: {r['year']}")
        if r["url"]: lines.append(f"  url: {r['url']}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--count", type=int, default=5)
    ap.add_argument("--format", choices=("yaml", "json"), default="yaml")
    args = ap.parse_args()

    load_dotenv()
    app_id = os.environ.get("CINII_APP_ID")
    if not app_id:
        print(
            "ERROR: CINII_APP_ID が未設定。リポジトリ直下の .env（gitignore 済み）に\n"
            "  CINII_APP_ID=<your-app-id>\n"
            "を記載するか、環境変数で渡すこと。",
            file=sys.stderr,
        )
        return 2

    results = search(args.query, args.count, app_id)
    if not results:
        print("該当なし", file=sys.stderr)
        return 1

    print(render_results(results, args.format), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
