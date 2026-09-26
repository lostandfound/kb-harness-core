"""本文 Markdown リンクの解決と書き換え。

本文リンクはリンク元ファイルからの相対パスで書く（`[名前](../people/example.md)`）。
GitHub・Obsidian・エディタのどれでもクリックで遷移できる形だからである。
旧形式の `content_root` 起点のルート相対リンク（`/people/example.md`）も解決はするが、
`kb validate` は移行を促す warning を出し、`kb link migrate` が相対リンクへ書き換える。

エンティティの識別子（relations の target、Claim の subject/object、ビューの members）は
リンクではないので、従来どおり `content_root` 起点のルート相対パスのままである。
"""

from __future__ import annotations

import posixpath
import re
from pathlib import Path

# URL 末尾の `.md` も拾うので、外部リンクは is_external で除外する
LINK_RE = re.compile(r"\]\(([^)\s#]+\.md)(#[^)\s]*)?\)")
SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


def body_links(body: str) -> list[str]:
    """本文中の `.md` へのローカルリンク先を出現順に返す（URL は除く）。"""
    return [match.group(1) for match in LINK_RE.finditer(body or "") if not is_external(match.group(1))]


def is_external(link: str) -> bool:
    """スキーム付き URL とプロトコル相対 URL（`//host/...`）。"""
    return bool(SCHEME_RE.match(link)) or link.startswith("//")


def is_root_relative(link: str) -> bool:
    return link.startswith("/") and not link.startswith("//")


def resolve_link(source: str, link: str) -> str | None:
    """リンクを `content_root` 起点の識別子（`/dir/name.md`）へ解決する。

    ``source`` はリンク元の識別子。相対リンクが `content_root` の外へ出るときは None。
    """
    parts = [] if is_root_relative(link) else [part for part in posixpath.dirname(source).split("/") if part]
    for part in link.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                return None
            parts.pop()
            continue
        parts.append(part)
    return "/" + "/".join(parts)


def relative_href(source: str, target: str) -> str:
    """識別子 ``source`` のファイルから識別子 ``target`` への相対リンクを返す。"""
    return posixpath.relpath(target, posixpath.dirname(source) or "/")


def relativize_body(source: str, text: str) -> str:
    """ルート相対リンクだけを相対リンクへ書き換える。相対リンクと URL はそのまま残す。"""

    def replace(match: re.Match[str]) -> str:
        link = match.group(1)
        if not is_root_relative(link):
            return match.group(0)
        target = resolve_link(source, link)
        fragment = match.group(2) or ""
        return f"]({relative_href(source, target)}{fragment})"

    return LINK_RE.sub(replace, text)


def rootify_body(source: str, text: str) -> str:
    """相対リンクを識別子（ルート相対）へ書き換える。画面側がリンク先を識別子で引くときに使う。

    画面は識別子でエンティティを引くので、見出しへのフラグメントは落とす。
    `content_root` の外へ出るリンクと URL はそのまま残す。
    """

    def replace(match: re.Match[str]) -> str:
        link = match.group(1)
        if is_external(link):
            return match.group(0)
        target = resolve_link(source, link)
        if target is None:
            return match.group(0)
        return f"]({target})"

    return LINK_RE.sub(replace, text)


def plan_link_migration(root: Path) -> dict[Path, str]:
    """`content_root` 配下の Markdown のルート相対リンクを相対リンクへ直す計画を返す。"""
    root = root.resolve()
    changes: dict[Path, str] = {}
    for path in sorted(root.rglob("*.md")):
        source = "/" + path.relative_to(root).as_posix()
        current = path.read_text(encoding="utf-8")
        rendered = relativize_body(source, current)
        if rendered != current:
            changes[path] = rendered
    return dict(sorted(changes.items(), key=lambda item: str(item[0])))
