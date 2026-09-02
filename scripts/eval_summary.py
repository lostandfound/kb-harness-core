#!/usr/bin/env python3
"""RAG 評価データセット（evals/rag-eval.yml）の決定論集計・退行検出。

rag-tester が history を追記した後、目視だけでは退行（過去 OK → 最新非 OK）を
見落としうるため、機械判定を挟んで CI・運用ループに組み込めるようにする。
"""
import argparse
import sys
from datetime import date, datetime
from pathlib import Path

import yaml

from kb_config import default_content_root

DEFAULT_EVAL_FILE = "evals/rag-eval.yml"
VERDICTS = ("OK", "曖昧", "回答不能", "誤答誘発")
# 非 OK の原因分類。by-design（争点ゆえ断定しないのが正しい挙動）だけは拡張候補にしない。
GAP_KINDS = ("missing-entity", "missing-relation", "missing-text", "retrieval", "by-design")
REQUIRED_FIELDS = ("id", "kind", "query", "expected", "evidence", "history")


def load_entries(path: Path) -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    return data if isinstance(data, list) else [data]


def validate_entries(entries: list[dict], evidence_root: Path | None = None) -> list[str]:
    """Return deterministic schema diagnostics for an evaluation dataset."""
    diagnostics: list[str] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        prefix = f"entry[{index}]"
        if not isinstance(entry, dict):
            diagnostics.append(f"{prefix}: entry must be a mapping")
            continue
        missing = [field for field in REQUIRED_FIELDS if field not in entry]
        diagnostics.extend(f"{prefix}: missing required field '{field}'" for field in missing)
        entry_id = _norm(entry.get("id"))
        if entry_id:
            if entry_id in seen:
                diagnostics.append(f"{prefix}: duplicate id '{entry_id}'")
            seen.add(entry_id)
        if not _norm(entry.get("query")):
            diagnostics.append(f"{prefix}: query must be non-empty")
        if not _norm(entry.get("expected")):
            diagnostics.append(f"{prefix}: expected must be non-empty")
        evidence = entry.get("evidence")
        if not isinstance(evidence, list) or not evidence or any(not _norm(path) for path in evidence):
            diagnostics.append(f"{prefix}: evidence must be a non-empty list of paths")
        elif evidence_root is not None:
            for raw_path in evidence:
                rel = _norm(raw_path)
                if not rel.startswith("/") or ".." in Path(rel).parts:
                    diagnostics.append(f"{prefix}: invalid evidence path '{rel}'")
                elif not (evidence_root / rel.lstrip("/")).is_file():
                    diagnostics.append(f"{prefix}: evidence path does not exist '{rel}'")
        history = entry.get("history")
        if not isinstance(history, list):
            diagnostics.append(f"{prefix}: history must be a list")
        else:
            for hidx, record in enumerate(history):
                if not isinstance(record, dict):
                    diagnostics.append(f"{prefix}.history[{hidx}]: record must be a mapping")
                    continue
                if _parse_date(record.get("date")) is None:
                    diagnostics.append(f"{prefix}.history[{hidx}]: date must be YYYY-MM-DD")
                if _norm(record.get("verdict")) not in VERDICTS:
                    diagnostics.append(f"{prefix}.history[{hidx}]: invalid verdict")
        gap = entry.get("gap")
        if gap is not None and _norm(gap) not in GAP_KINDS:
            diagnostics.append(f"{prefix}: invalid gap")
    return diagnostics


def _norm(value) -> str:
    return str(value).strip() if value is not None else ""


def _parse_date(value) -> date | None:
    try:
        return datetime.strptime(_norm(value), "%Y-%m-%d").date()
    except ValueError:
        return None


def filter_history_since(entries: list[dict], since: str | None) -> list[dict]:
    """--since 指定時、各エントリの history を since 以降の記録に絞り込む。

    history が空になったエントリは後続の集計で自然に「履歴なし」として扱われる。
    """
    if not since:
        return entries
    since_d = _parse_date(since)
    if since_d is None:
        return entries
    filtered = []
    for entry in entries:
        history = entry.get("history") or []
        kept = [h for h in history if (_parse_date(h.get("date")) or date.min) >= since_d]
        new_entry = dict(entry)
        new_entry["history"] = kept
        filtered.append(new_entry)
    return filtered


def latest_record(entry: dict) -> dict | None:
    """entry の history 末尾を返す（date/verdict を trim 済みで返す）。履歴なしなら None。"""
    history = entry.get("history") or []
    if not history:
        return None
    last = history[-1]
    return {"date": _norm(last.get("date")), "verdict": _norm(last.get("verdict"))}


def summarize_latest(entries: list[dict]) -> dict:
    """最新判定の全体集計と kind 別集計を返す。

    戻り値: {"total": int, "evaluated": int, "by_verdict": {...},
             "by_kind": {kind: {"total": int, "by_verdict": {...}}}}
    """
    by_verdict = {v: 0 for v in VERDICTS}
    by_kind: dict[str, dict] = {}
    evaluated = 0
    for entry in entries:
        kind = _norm(entry.get("kind")) or "(不明)"
        by_kind.setdefault(kind, {"total": 0, "by_verdict": {v: 0 for v in VERDICTS}})
        by_kind[kind]["total"] += 1
        rec = latest_record(entry)
        if rec is None:
            continue
        evaluated += 1
        verdict = rec["verdict"]
        by_verdict[verdict] = by_verdict.get(verdict, 0) + 1
        by_kind[kind]["by_verdict"][verdict] = by_kind[kind]["by_verdict"].get(verdict, 0) + 1
    return {
        "total": len(entries),
        "evaluated": evaluated,
        "by_verdict": by_verdict,
        "by_kind": by_kind,
    }


def find_regressions(entries: list[dict]) -> list[dict]:
    """「過去に OK があり、最新が OK でない」設問を抽出する。

    直近の OK（最新記録より前で最も新しい OK）の日付を添えて返す。
    """
    regressions = []
    for entry in entries:
        history = entry.get("history") or []
        if not history:
            continue
        latest = history[-1]
        latest_verdict = _norm(latest.get("verdict"))
        if latest_verdict == "OK":
            continue
        last_ok = None
        for h in history[:-1]:
            if _norm(h.get("verdict")) == "OK":
                last_ok = h
        if last_ok is None:
            continue
        regressions.append(
            {
                "id": entry.get("id"),
                "query": entry.get("query"),
                "last_ok_date": _norm(last_ok.get("date")),
                "latest_date": _norm(latest.get("date")),
                "latest_verdict": latest_verdict,
            }
        )
    return regressions


def find_stale(entries: list[dict], stale_days: int = 30) -> list[dict]:
    """全体の最新評価日から stale_days 日以上古い最終評価しか持たない設問を返す。

    history が空のエントリ（未評価）は対象外（判定不能のため）とする。
    """
    dated = []
    for entry in entries:
        rec = latest_record(entry)
        if rec is None:
            continue
        d = _parse_date(rec["date"])
        if d is None:
            continue
        dated.append((entry, d))
    if not dated:
        return []
    overall_latest = max(d for _, d in dated)
    stale = []
    for entry, d in dated:
        if (overall_latest - d).days >= stale_days:
            stale.append({"id": entry.get("id"), "date": d.isoformat(), "days": (overall_latest - d).days})
    return stale


def find_open_gaps(entries: list[dict]) -> list[dict]:
    """最新 verdict が OK でない設問のうち、拡張候補になりうるものを返す。

    gap が by-design のものは KB として正しい挙動なので除外する。gap 未設定・
    語彙外の値は未分類として返し、分類を促す（invalid_gap に元の値を残す）。
    """
    open_gaps = []
    for entry in entries:
        rec = latest_record(entry)
        if rec is None:
            continue
        if rec["verdict"] == "OK":
            continue
        gap = _norm(entry.get("gap"))
        if gap == "by-design":
            continue
        open_gaps.append(
            {
                "id": entry.get("id"),
                "kind": entry.get("kind"),
                "query": entry.get("query"),
                "date": rec["date"],
                "verdict": rec["verdict"],
                "gap": gap if gap in GAP_KINDS else "",
                "invalid_gap": "" if gap in GAP_KINDS else gap,
                "evidence": entry.get("evidence") or [],
            }
        )
    return open_gaps


def format_open_lines(open_gaps: list[dict]) -> list[str]:
    """未解決の欠落を docs/BACKLOG.md へ転記しやすい 1 行形式にする。"""
    lines = []
    for g in open_gaps:
        evidence = " / ".join(str(e) for e in g["evidence"]) or "なし"
        lines.append(
            "- [ ] {id} ({kind}): {query} — {verdict}（{date}）。gap: {gap}。evidence: {evidence}".format(
                id=g["id"],
                kind=g["kind"],
                query=g["query"],
                verdict=g["verdict"],
                date=g["date"],
                gap=g["gap"] or "未分類",
                evidence=evidence,
            )
        )
    return lines


def format_report(entries: list[dict], stale_days: int) -> str:
    summary = summarize_latest(entries)
    lines = []

    bv = summary["by_verdict"]
    lines.append(
        "最新: OK {ok} / 曖昧 {amb} / 回答不能 {una} / 誤答誘発 {mis}（全{total}問）".format(
            ok=bv.get("OK", 0),
            amb=bv.get("曖昧", 0),
            una=bv.get("回答不能", 0),
            mis=bv.get("誤答誘発", 0),
            total=summary["total"],
        )
    )
    for kind in sorted(summary["by_kind"]):
        kbv = summary["by_kind"][kind]["by_verdict"]
        lines.append(
            "  {kind}: OK {ok} / 曖昧 {amb} / 回答不能 {una} / 誤答誘発 {mis}（{total}問）".format(
                kind=kind,
                ok=kbv.get("OK", 0),
                amb=kbv.get("曖昧", 0),
                una=kbv.get("回答不能", 0),
                mis=kbv.get("誤答誘発", 0),
                total=summary["by_kind"][kind]["total"],
            )
        )

    lines.append("")
    regressions = find_regressions(entries)
    if regressions:
        for r in regressions:
            lines.append(
                "REGRESSION {id}: {last_ok_date} OK → {latest_date} {verdict}  {query}".format(
                    id=r["id"],
                    last_ok_date=r["last_ok_date"],
                    latest_date=r["latest_date"],
                    verdict=r["latest_verdict"],
                    query=r["query"],
                )
            )
    else:
        lines.append("退行なし")

    lines.append("")
    open_gaps = find_open_gaps(entries)
    lines.append(f"未解決の欠落（by-design 除く）: {len(open_gaps)}件")
    for line in format_open_lines(open_gaps):
        lines.append(f"  {line}")

    lines.append("")
    stale = find_stale(entries, stale_days=stale_days)
    lines.append(f"未評価の古い設問（{stale_days}日以上）: {len(stale)}件")
    for s in stale:
        lines.append(f"  {s['id']}: 最終評価 {s['date']}（{s['days']}日前）")

    return "\n".join(lines), bool(regressions)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval-file", default=DEFAULT_EVAL_FILE, help="評価データセット YAML のパス")
    parser.add_argument("--since", default=None, help="YYYY-MM-DD 以降の history のみを対象に集計する")
    parser.add_argument("--stale-days", type=int, default=30, help="未評価とみなす経過日数の閾値")
    parser.add_argument(
        "--open",
        action="store_true",
        dest="open_only",
        help="未解決の欠落のみを BACKLOG 転記用の行形式で出力する（退行検出の exit code は据え置き）",
    )
    args = parser.parse_args(argv)

    path = Path(args.eval_file)
    if not path.exists():
        print(f"評価ファイルが見つからない: {path}", file=sys.stderr)
        return 2

    entries = load_entries(path)
    diagnostics = validate_entries(entries, evidence_root=Path(default_content_root()))
    if diagnostics:
        for diagnostic in diagnostics:
            print(f"INVALID {diagnostic}", file=sys.stderr)
        return 1
    entries = filter_history_since(entries, args.since)

    if args.open_only:
        for line in format_open_lines(find_open_gaps(entries)):
            print(line)
        return 1 if find_regressions(entries) else 0

    report, has_regression = format_report(entries, args.stale_days)
    print(report)
    return 1 if has_regression else 0


if __name__ == "__main__":
    raise SystemExit(main())
