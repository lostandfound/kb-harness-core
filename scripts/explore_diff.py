#!/usr/bin/env python3
"""Wikipedia カテゴリと KB 収録の機械的差分を出す（探索ループの経路A）。

使い方:
  python3 scripts/explore_diff.py ["<カテゴリ名>" ...] [--depth 0] [--root <content_root>] [--include-lists]

カテゴリを省略した場合は kb-domain.yml の exploration.wikipedia_categories を読む。
MediaWiki API（action=query&list=categorymembers）でカテゴリ所属記事タイトルを取得し、
KB 側の全エンティティ frontmatter の title / aliases と突き合わせて未収録候補を抽出する。
一致判定は完全一致に加え、括弧註釈（例:「宮城長順 (空手家)」→「宮城長順」）を除去した
正規化一致も見る。判定・裏取りは行わない（機械的な列挙のみ）。

「〜一覧」で終わる記事や「Category:」「Template:」等の名前空間付きタイトルは、単体エンティティ
ではなくメタ的な記事であり収録候補として扱いにくいため既定で除外する（`--include-lists` で無効化）。
MediaWiki API 呼び出しが 429/503 を返した場合は指数バックオフ（初回2秒、最大3リトライ）で再試行し、
それでも失敗すれば明確なエラーで終了する。
"""
import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

from kb_config import default_content_root

API_URL = "https://ja.wikipedia.org/w/api.php"
USER_AGENT = "kb-harness-explore/1.0"
PAREN_RE = re.compile(r"\s*[（(][^（）()]*[）)]\s*$")
LIST_TITLE_RE = re.compile(r"(の一覧|一覧)$")
RETRYABLE_STATUSES = {429, 503}
MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 2.0


def normalize_title(title: str) -> str:
    """括弧註釈を除去して比較用に正規化する（例:「宮城長順 (空手家)」→「宮城長順」）。"""
    return PAREN_RE.sub("", title).strip()


def is_list_or_meta_title(title: str) -> bool:
    """一覧記事（「〜一覧」）または名前空間付き（「Category:」等コロン含み）タイトルか判定する。"""
    return bool(LIST_TITLE_RE.search(title)) or ":" in title


def fetch_with_retry(url: str) -> dict:
    """MediaWiki API を呼び出す。429/503 は指数バックオフで最大 MAX_RETRIES 回再試行する。"""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    backoff = INITIAL_BACKOFF_SECONDS
    for attempt in range(MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code not in RETRYABLE_STATUSES or attempt == MAX_RETRIES:
                raise SystemExit(
                    f"MediaWiki API 呼び出しが失敗した（HTTP {e.code}、{attempt + 1} 回試行）: {url}"
                ) from e
            print(
                f"WARN MediaWiki API HTTP {e.code}、{backoff:.0f}秒後にリトライ"
                f"（{attempt + 1}/{MAX_RETRIES}）",
                file=sys.stderr,
            )
            time.sleep(backoff)
            backoff *= 2
    raise SystemExit(f"MediaWiki API 呼び出しが失敗した: {url}")


def fetch_category_members(category: str, depth: int = 0, _seen: set[str] | None = None) -> list[str]:
    """カテゴリ所属記事タイトルの一覧を取得する。depth > 0 でサブカテゴリも展開する。"""
    if _seen is None:
        _seen = set()
    if category in _seen:
        return []
    _seen.add(category)

    titles: list[str] = []
    subcats: list[str] = []
    cmcontinue = None
    while True:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": f"Category:{category}",
            "cmlimit": "500",
            "format": "json",
        }
        if cmcontinue:
            params["cmcontinue"] = cmcontinue
        data = fetch_with_retry(f"{API_URL}?{urllib.parse.urlencode(params)}")

        for member in data.get("query", {}).get("categorymembers", []):
            title = member.get("title", "")
            if title.startswith("Category:"):
                subcats.append(title[len("Category:") :])
            else:
                titles.append(title)

        cmcontinue = data.get("continue", {}).get("cmcontinue")
        if not cmcontinue:
            break

    if depth > 0:
        for sub in subcats:
            titles.extend(fetch_category_members(sub, depth - 1, _seen))

    return titles


def collect_kb_names(root: Path) -> set[str]:
    """root 配下の全エンティティ frontmatter から title と aliases を集める（正規化前の生の文字列）。"""
    names: set[str] = set()
    for path in sorted(root.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        m = re.match(r"\A---\n(.*?)\n---\n?", text, re.DOTALL)
        if not m:
            continue
        try:
            fm = yaml.safe_load(m.group(1))
        except yaml.YAMLError:
            continue
        if not isinstance(fm, dict):
            continue
        title = fm.get("title")
        if isinstance(title, str) and title.strip():
            names.add(title.strip())
        for alias in fm.get("aliases") or []:
            if isinstance(alias, str) and alias.strip():
                names.add(alias.strip())
    return names


def diff_titles(wiki_titles: list[str], kb_names: set[str], include_lists: bool = False) -> list[str]:
    """KB 側に一致しない Wikipedia 記事タイトルを、出現順を保って重複除去し返す。

    include_lists=False（既定）では一覧記事・名前空間付きタイトルも除外する。
    """
    normalized_kb = {normalize_title(n) for n in kb_names} | kb_names
    unmatched: list[str] = []
    seen: set[str] = set()
    for title in wiki_titles:
        if title in seen:
            continue
        seen.add(title)
        if not include_lists and is_list_or_meta_title(title):
            continue
        if title in kb_names or normalize_title(title) in normalized_kb:
            continue
        unmatched.append(title)
    return unmatched


def load_default_categories(root: Path) -> list[str]:
    kb_domain_path = root.parent / "kb-domain.yml"
    if not kb_domain_path.exists():
        raise SystemExit(f"カテゴリ未指定かつ kb-domain.yml が見つからない: {kb_domain_path}")
    data = yaml.safe_load(kb_domain_path.read_text(encoding="utf-8")) or {}
    categories = ((data.get("exploration") or {}).get("wikipedia_categories")) or []
    if not categories:
        raise SystemExit(
            "カテゴリ未指定かつ kb-domain.yml に exploration.wikipedia_categories が定義されていない"
        )
    return categories


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("categories", nargs="*", help="Wikipedia カテゴリ名（省略時は kb-domain.yml から読む）")
    ap.add_argument("--depth", type=int, default=0, help="サブカテゴリの展開深さ（既定 0 = 展開しない）")
    ap.add_argument("--root", default=None, help="KB コンテンツルート（省略時は kb-domain.yml から解決）")
    ap.add_argument(
        "--include-lists",
        action="store_true",
        help="「〜一覧」記事・名前空間付きタイトルも候補に含める（既定は除外）",
    )
    args = ap.parse_args()

    root = Path(args.root) if args.root else Path(default_content_root())
    categories = args.categories or load_default_categories(root)
    kb_names = collect_kb_names(root)

    total_fetched = 0
    for category in categories:
        wiki_titles = fetch_category_members(category, depth=args.depth)
        total_fetched += len(wiki_titles)
        unmatched = diff_titles(wiki_titles, kb_names, include_lists=args.include_lists)
        excluded_lists = (
            0
            if args.include_lists
            else sum(1 for t in wiki_titles if is_list_or_meta_title(t))
        )
        print(
            f"# Category:{category}（取得 {len(wiki_titles)} 件 / 一覧・名前空間除外 {excluded_lists} 件 "
            f"/ 未収録候補 {len(unmatched)} 件）",
            file=sys.stderr,
        )
        for title in unmatched:
            url = f"https://ja.wikipedia.org/wiki/{urllib.parse.quote(title)}"
            print(f"- {title}\t{url}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
