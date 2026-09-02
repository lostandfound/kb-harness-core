#!/usr/bin/env python3
"""NDL サーチ OpenSearch API で書籍・資料を検索し、references.yml 登録用の YAML を出力する。

使い方:
  python3 scripts/ndl_search.py "<ドメインのキーワード>" [--count 5] [--title-only] [--mediatype books]

国立国会図書館サーチの API は認証不要。書籍・雑誌など単行資料の書誌確認に使う
（論文は scripts/cinii_search.py を使う）。
"""
import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

API = "https://ndlsearch.ndl.go.jp/api/opensearch"
NS = {
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcterms": "http://purl.org/dc/terms/",
    "dcndl": "http://ndl.go.jp/dcndl/terms/",
}


def slugify(author: str, year: str, url: str = "") -> str:
    # 日本語著者名は決定論的にローマ字化できないため、ASCII 化で空になる場合は
    # NDL 書誌 ID 末尾を仮 ID に使う（いずれもユーザー編集前提）
    base = re.sub(r"[^a-z0-9]+", "-", author.lower()).strip("-")
    if not base:
        m = re.search(r"/books/([A-Za-z0-9-]+)", url)
        base = f"ndl{m.group(1)[-6:].lower()}" if m else "ref"
    return f"{base}-{year}" if year else base


def search(query: str, count: int, title_only: bool, mediatype: str) -> list[dict]:
    params = {"cnt": count}
    params["title" if title_only else "any"] = query
    if mediatype:
        params["mediatype"] = mediatype
    req = urllib.request.Request(
        f"{API}?{urllib.parse.urlencode(params)}",
        headers={"User-Agent": "kb-harness-ndl/1.0"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        root = ET.fromstring(resp.read())
    results = []
    for item in root.iter("item"):
        title = item.findtext("title") or ""
        authors = [e.text for e in item.findall("dc:creator", NS) if e.text] or [
            e.text for e in item.findall("author") if e.text
        ]
        publisher = item.findtext("dc:publisher", default="", namespaces=NS)
        issued = item.findtext("dcterms:issued", default="", namespaces=NS) or item.findtext(
            "dc:date", default="", namespaces=NS
        )
        # NDL の刊行年は全角数字の場合がある（例: １９７５）ため半角へ正規化する
        issued = issued.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
        year_m = re.search(r"[0-9]{4}", issued)
        link = item.findtext("guid") or item.findtext("link") or ""
        results.append(
            {
                "title": title,
                "authors": authors,
                "publisher": publisher,
                "year": year_m.group(0) if year_m else "",
                "url": link,
            }
        )
    return results


def render_results(results: list[dict], output_format: str = "yaml") -> str:
    """Render search results; JSON is directly consumable by ``reference spec``."""
    if output_format == "json":
        items = [{**r, "type": "book"} for r in results]
        return json.dumps({"results": items}, ensure_ascii=False, indent=2) + "\n"
    lines = []
    for r in results:
        author = "、".join(r["authors"]) if r["authors"] else "不明"
        ref_id = slugify(r["authors"][0] if r["authors"] else "ref", r["year"], r["url"])
        lines.extend([f"# --- references.yml 登録案（ID は要編集: {ref_id}） ---", f"{ref_id}:", "  type: book", f"  author: {author}", f"  title: {r['title']}"])
        if r["publisher"]: lines.append(f"  publisher: {r['publisher']}")
        if r["year"]: lines.append(f"  year: {r['year']}")
        if r["url"]: lines.append(f"  url: {r['url']}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--count", type=int, default=5)
    ap.add_argument("--title-only", action="store_true", help="タイトルのみを検索対象にする")
    ap.add_argument("--mediatype", default="books", help="books/periodicals 等。空文字で全種別")
    ap.add_argument("--format", choices=("yaml", "json"), default="yaml")
    args = ap.parse_args()

    results = search(args.query, args.count, args.title_only, args.mediatype)
    if not results:
        print("該当なし", file=sys.stderr)
        return 1

    print(render_results(results, args.format), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
