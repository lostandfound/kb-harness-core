#!/usr/bin/env python3
"""文献レジストリ（references.yml）の健全性点検。

Web 資料はリンク切れと改訂が静かに起こり、pending（実見待ち等の先行登録）は
理由だけを持ち滞留期間が分からない。いずれも検証では検出されず件数に丸められる
ため、最終確認日と滞留期間を持たせて表面化させる。
"""

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

import yaml

DEFAULT_REFS = "okinawa-karate/references.yml"


def load_references(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {k: v for k, v in data.items() if isinstance(v, dict)}


def _parse_date(value) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def pending_entries(refs: dict, today: date) -> list[dict]:
    """pending の文献を滞留日数付きで返す。since 未記載は日数不明として残す。"""
    out = []
    for ref_id, entry in refs.items():
        if not entry.get("pending"):
            continue
        since = _parse_date(entry.get("since"))
        out.append(
            {
                "id": ref_id,
                "reason": entry.get("pending"),
                "since": since.isoformat() if since else "",
                "age_days": (today - since).days if since else None,
            }
        )
    return out


def stale_urls(refs: dict, today: date, stale_days: int) -> list[dict]:
    """到達確認が古い、または一度も記録されていない URL を返す。"""
    out = []
    for ref_id, entry in refs.items():
        url = entry.get("url")
        if not url:
            continue
        checked = _parse_date(entry.get("checked"))
        if checked is not None and (today - checked).days < stale_days:
            continue
        out.append(
            {
                "id": ref_id,
                "url": url,
                "checked": checked.isoformat() if checked else "",
                "days": (today - checked).days if checked else None,
            }
        )
    return out


def summarize(refs: dict, today: date, stale_days: int) -> dict:
    by_type: dict[str, int] = {}
    for entry in refs.values():
        t = entry.get("type") or "不明"
        by_type[t] = by_type.get(t, 0) + 1
    pend = pending_entries(refs, today)
    return {
        "total": len(refs),
        "by_type": by_type,
        "pending": len(pend),
        "pending_without_since": sum(1 for p in pend if p["age_days"] is None),
        "with_url": sum(1 for e in refs.values() if e.get("url")),
        "never_checked": sum(1 for e in refs.values() if e.get("url") and not _parse_date(e.get("checked"))),
        "stale": len(stale_urls(refs, today, stale_days)),
    }


def record_checks(text: str, results: dict) -> str:
    """到達確認できた文献の checked を行単位で更新する。

    YAML を再出力すると整形・引用符・並び順が変わり差分が読めなくなるため、
    該当行だけを書き換える。
    """
    if not results:
        return text
    lines = text.split("\n")
    out = []
    current = None
    pending_insert = {}
    for line in lines:
        if line and not line.startswith((" ", "-", "#")) and line.rstrip().endswith(":"):
            current = line.rstrip()[:-1]
        if current in results and line.startswith("  checked:"):
            out.append(f"  checked: {results[current]}")
            pending_insert[current] = False
            continue
        out.append(line)
        if current in results and line.startswith("  url:"):
            pending_insert.setdefault(current, True)
    if not any(pending_insert.values()):
        return "\n".join(out)

    # url 行の直後に checked を挿入する（checked 行を持たなかった文献のみ）
    final = []
    current = None
    for line in out:
        if line and not line.startswith((" ", "-", "#")) and line.rstrip().endswith(":"):
            current = line.rstrip()[:-1]
        final.append(line)
        if pending_insert.get(current) and line.startswith("  url:"):
            final.append(f"  checked: {results[current]}")
    return "\n".join(final)


def format_report(refs: dict, today: date, stale_days: int) -> str:
    s = summarize(refs, today, stale_days)
    lines = [f"文献 {s['total']}件（URL あり {s['with_url']}件）"]
    for t in sorted(s["by_type"]):
        lines.append(f"  {t}: {s['by_type'][t]}")
    lines.append("")
    lines.append(f"pending: {s['pending']}件（うち since 未記載 {s['pending_without_since']}件）")
    for p in sorted(pending_entries(refs, today), key=lambda x: (x["age_days"] is None, -(x["age_days"] or 0))):
        age = f"{p['age_days']}日" if p["age_days"] is not None else "不明"
        lines.append(f"  {p['id']}: {p['reason']}（滞留 {age}）")
    lines.append("")
    lines.append(f"到達確認が {stale_days} 日以上前 または未記録: {s['stale']}件（未記録 {s['never_checked']}件）")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refs", default=DEFAULT_REFS, help="文献レジストリのパス")
    parser.add_argument("--stale-days", type=int, default=180, help="到達確認が古いとみなす経過日数")
    parser.add_argument("--pending", action="store_true", help="pending の文献のみを滞留日数順に出力する")
    parser.add_argument(
        "--record-check",
        action="store_true",
        help="到達確認を実行し、成功した文献の checked を更新する（ネットワークを使う）",
    )
    args = parser.parse_args(argv)

    path = Path(args.refs)
    if not path.exists():
        print(f"文献レジストリが見つからない: {path}", file=sys.stderr)
        return 2

    refs = load_references(path)
    today = date.today()

    if args.record_check:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from validate import _url_reachable

        results = {}
        unreachable = []
        for e in stale_urls(refs, today, args.stale_days):
            if _url_reachable(e["url"]):
                results[e["id"]] = today.isoformat()
            else:
                unreachable.append(e)
        path.write_text(record_checks(path.read_text(encoding="utf-8"), results), encoding="utf-8")
        print(f"到達確認 {len(results)}件を記録した")
        for e in unreachable:
            print(f"UNREACHABLE {e['id']}: {e['url']}")
        return 1 if unreachable else 0

    if args.pending:
        for p in sorted(pending_entries(refs, today), key=lambda x: (x["age_days"] is None, -(x["age_days"] or 0))):
            age = f"{p['age_days']}日" if p["age_days"] is not None else "不明"
            print(f"{p['id']}: {p['reason']}（滞留 {age}）")
        return 0

    print(format_report(refs, today, args.stale_days))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
