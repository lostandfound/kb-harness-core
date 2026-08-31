#!/usr/bin/env python3
"""懸念台帳（docs/CONCERNS.md）の状態別集計と、着手可能な懸念の抽出。

台帳は解決/未解決の 2 値しか持たず、着手できるもの、一次資料の入手待ちで
着手できないもの、史料的に決着不能で記述側は完了しているものが混在していた。
状態を明示して機械的に分離し、周期ごとに拾うべき懸念だけを取り出す。
"""

import argparse
import re
import sys
from pathlib import Path

DEFAULT_LEDGER = "docs/CONCERNS.md"

# 懸念の状態。settled-hedged は「史料的に決着せず、両論併記・ヘッジで記述側は完了」を指し、
# 未解決に見えて作業対象ではない。suspended は再開条件付きの打ち切り。
STATUSES = (
    "open",
    "investigating",
    "blocked-source",
    "settled-hedged",
    "suspended",
    "resolved",
)

# 着手対象から外す状態。resolved 以外は「未解決だが今は動かせない」もの。
INACTIVE = ("blocked-source", "settled-hedged", "suspended", "resolved")

_LINE = re.compile(r"^- \[( |x)\] (.*)$")
_STATUS = re.compile(r"status:\s*([A-Za-z-]+)\s*$")


def parse_concerns(text: str) -> list[dict]:
    """台帳本文からチェックボックス行を抽出する。

    status タグ未設定・語彙外の値は未分類として返し、元の値を invalid_status に残す。
    分類漏れを黙って通すと、着手可能な懸念が抽出結果から消えるため。
    """
    entries = []
    for line in text.split("\n"):
        m = _LINE.match(line.rstrip())
        if not m:
            continue
        body = m.group(2)
        sm = _STATUS.search(body)
        raw_status = sm.group(1) if sm else ""
        target = body.split(":", 1)[0].strip() if ":" in body else ""
        entries.append(
            {
                "done": m.group(1) == "x",
                "target": target,
                "body": body,
                "status": raw_status if raw_status in STATUSES else "",
                "invalid_status": "" if raw_status in STATUSES else raw_status,
            }
        )
    return entries


def actionable(entries: list[dict]) -> list[dict]:
    """いま調査に着手できる懸念だけを返す。未分類は含める（分類を促すため）。"""
    return [e for e in entries if not e["done"] and e["status"] not in INACTIVE]


def summarize(entries: list[dict]) -> dict:
    by_status = {s: 0 for s in STATUSES}
    unclassified = 0
    for e in entries:
        if e["status"]:
            by_status[e["status"]] += 1
        else:
            unclassified += 1
    return {"total": len(entries), "by_status": by_status, "unclassified": unclassified}


def format_report(entries: list[dict]) -> str:
    summary = summarize(entries)
    lines = [f"懸念 {summary['total']}件"]
    for s in STATUSES:
        lines.append(f"  {s}: {summary['by_status'][s]}")
    lines.append(f"  未分類: {summary['unclassified']}")
    lines.append("")
    act = actionable(entries)
    lines.append(f"着手可能: {len(act)}件")
    for e in act:
        lines.append(f"  [{e['status'] or '未分類'}] {e['target'] or e['body'][:40]}")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", default=DEFAULT_LEDGER, help="懸念台帳のパス")
    parser.add_argument(
        "--actionable",
        action="store_true",
        help="着手可能な懸念のみを 1 行ずつ出力する",
    )
    args = parser.parse_args(argv)

    path = Path(args.ledger)
    if not path.exists():
        print(f"懸念台帳が見つからない: {path}", file=sys.stderr)
        return 2

    entries = parse_concerns(path.read_text(encoding="utf-8"))
    if args.actionable:
        for e in actionable(entries):
            print(f"[{e['status'] or '未分類'}] {e['body']}")
    else:
        print(format_report(entries))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
