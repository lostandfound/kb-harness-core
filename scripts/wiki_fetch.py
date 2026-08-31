#!/usr/bin/env python3
"""MediaWiki API で Wikipedia 記事のプレーンテキスト全文を取得する。

使い方:
  python3 scripts/wiki_fetch.py "<人物名>" [--lang ja] [--sections]

WebFetch は要約を挟み全文を取得できないため、考証（生没年・系譜の裏取り）では
本スクリプトで原文を確認する。取得した本文の転載・翻案は禁止（裏取り用途のみ）。
"""
import argparse
import json
import sys
import urllib.parse
import urllib.request


def fetch(title: str, lang: str) -> dict | None:
    params = urllib.parse.urlencode(
        {
            "action": "query",
            "prop": "extracts|info",
            "explaintext": 1,
            "redirects": 1,
            "format": "json",
            "titles": title,
        }
    )
    req = urllib.request.Request(
        f"https://{lang}.wikipedia.org/w/api.php?{params}",
        headers={"User-Agent": "kb-harness-wiki/1.0"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.load(resp)
    pages = data.get("query", {}).get("pages", {})
    for page_id, page in pages.items():
        if page_id != "-1" and "extract" in page:
            return page
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("title")
    ap.add_argument("--lang", default="ja")
    args = ap.parse_args()

    page = fetch(args.title, args.lang)
    if page is None:
        print(f"該当なし: {args.title}", file=sys.stderr)
        return 1

    url = f"https://{args.lang}.wikipedia.org/wiki/{urllib.parse.quote(page['title'])}"
    print(f"# {page['title']}")
    print(f"# URL: {url}")
    print()
    print(page["extract"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
