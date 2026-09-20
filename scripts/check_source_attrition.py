#!/usr/bin/env python3
"""既存エンティティの改版で、先行する出典の記述が失われていないかを検出する。

複数の出典を並存させるエンティティを改版すると、新しい出典に沿って本文を書き直す
過程で先行出典の段落がまとめて消えることがある。形式は正しいままなので kb validate
は通り、差分を読まない限り気づけない。ここでは主張単位の出典表記（出典: <ref-id>）
の数を改版前と突き合わせ、ある出典の記述が丸ごと消えた場合に限って止める。

推敲による部分的な減少は日常的に起きるため既定では見逃す。すべての減少を検出したい
場合は --strict を使う。意図してある出典の記述を落とすときは、環境変数
KB_ALLOW_SOURCE_ATTRITION=1 を付けて実行する。
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

ATTRIBUTION = re.compile(r"（出典:\s*([^）]+)）")
FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


def _front_matter_refs(text: str) -> set[str]:
    """front matter の sources に並ぶ ref-id を返す。sources がなければ空集合。"""
    match = FRONT_MATTER.match(text)
    if not match:
        return set()
    try:
        data = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return set()
    refs = set()
    for source in data.get("sources") or []:
        if isinstance(source, str) and source.startswith("ref:"):
            refs.add(source.split(":", 1)[1].strip())
    return refs


def _attribution_counts(text: str) -> dict[str, int]:
    """本文中の (出典: ...) を ref-id ごとに数える。括弧内は ASCII カンマ区切り。"""
    counts: dict[str, int] = {}
    body = FRONT_MATTER.sub("", text)
    for inner in ATTRIBUTION.findall(body):
        for ref in inner.split(","):
            ref = ref.strip()
            if ref:
                counts[ref] = counts.get(ref, 0) + 1
    return counts


def detect_attrition(before: str, after: str, strict: bool = False) -> list[tuple[str, int, int]]:
    """失われた出典を (ref-id, 改版前の件数, 改版後の件数) で返す。

    対象は改版前の front matter が sources に挙げている ref-id に限る。front matter を
    持たない文書や、sources のない文書は判定しない。
    """
    declared = _front_matter_refs(before)
    if not declared:
        return []
    still_declared = _front_matter_refs(after)
    before_counts = _attribution_counts(before)
    after_counts = _attribution_counts(after)
    lost = []
    for ref in sorted(declared):
        was = before_counts.get(ref, 0)
        # sources から外された出典は、本文に表記が残っていても裏づけを失ったものとして扱う。
        # WHY: 本文の表記だけが残る状態を kb validate は検出しない。
        now = 0 if ref not in still_declared else after_counts.get(ref, 0)
        if was == 0:
            continue
        # 過半が消えたら改版ではなく差し替えとみなす。推敲でまとめた程度の減少は見逃す。
        if now * 2 < was or (strict and now < was):
            lost.append((ref, was, now))
    return lost


def _staged_markdown(repo_root: Path) -> list[str]:
    """ステージ済みの変更ファイルのうち Markdown を返す。新規追加は比較対象がないので除く。"""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=M"],
        cwd=repo_root, capture_output=True, text=True, check=True,
    )
    return [line for line in result.stdout.splitlines() if line.endswith(".md")]


def _base_version(repo_root: Path, base: str, path: str) -> str | None:
    result = subprocess.run(
        ["git", "show", f"{base}:{path}"], cwd=repo_root, capture_output=True, text=True,
    )
    return result.stdout if result.returncode == 0 else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="検査するファイル（既定はステージ済みの変更）")
    parser.add_argument("--base", default="HEAD", help="比較対象のリビジョン（既定: HEAD）")
    parser.add_argument("--strict", action="store_true", help="件数が減っただけでも失敗させる")
    args = parser.parse_args(argv)

    if os.environ.get("KB_ALLOW_SOURCE_ATTRITION"):
        return 0

    repo_root = Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
        ).stdout.strip()
    )
    paths = args.paths or _staged_markdown(repo_root)

    failures = []
    for path in paths:
        current_file = repo_root / path
        if not current_file.exists():
            continue
        before = _base_version(repo_root, args.base, path)
        if before is None:
            continue
        after = current_file.read_text(encoding="utf-8")
        for ref, was, now in detect_attrition(before, after, strict=args.strict):
            failures.append((path, ref, was, now))

    if not failures:
        return 0

    print("出典の記述が失われています。改版前の段落を復元してください。", file=sys.stderr)
    for path, ref, was, now in failures:
        print(f"  {path}: 出典 {ref} の記述が {was} 件から {now} 件になりました", file=sys.stderr)
    print(
        "意図した削除であれば KB_ALLOW_SOURCE_ATTRITION=1 を付けて再実行してください。",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
