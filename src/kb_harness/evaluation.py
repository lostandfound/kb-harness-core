"""RAG 評価（evals/rag-eval.yml）の集計・退行検出と、字面検索スモーク。

`kb eval summary` / `kb eval smoke` と、互換入口 `scripts/eval_summary.py` /
`scripts/rag_smoke.py` の両方がここを呼ぶ。ロジックはここにだけ置く。
"""
from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

DEFAULT_EVAL_FILE = "evals/rag-eval.yml"
VERDICTS = ("OK", "曖昧", "回答不能", "誤答誘発")
# 非 OK の原因分類。by-design（争点ゆえ断定しないのが正しい挙動）だけは拡張候補にしない。
GAP_KINDS = ("missing-entity", "missing-relation", "missing-text", "retrieval", "by-design")
REQUIRED_FIELDS = ("id", "kind", "query", "expected", "evidence", "history")


def load_entries(path: Path) -> list[dict]:
    """評価データセットを読む。トップレベルはエントリの list か、`entries` キーを持つ mapping。"""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if isinstance(data, dict):
        data = data.get("entries") or []
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


def _ngrams(text: str, size: int = 2) -> set[str]:
    normalized = re.sub(r"[^0-9a-zA-Z一-龥ぁ-んァ-ヶ]+", "", text).lower()
    if len(normalized) < size:
        return {normalized} if normalized else set()
    return {normalized[i : i + size] for i in range(len(normalized) - size + 1)}


def _title(text: str) -> str:
    match = re.search(r"(?m)^title:\s*(.+)$", text)
    return match.group(1).strip() if match else ""


def rank_documents(query: str, documents: dict[str, str], limit: int = 5) -> list[str]:
    query_grams = _ngrams(query)
    scored = []
    for path, text in documents.items():
        body_overlap = len(query_grams & _ngrams(text))
        title_overlap = len(query_grams & _ngrams(_title(text)))
        # A generic domain word in a title should not outrank a document whose
        # body matches most of the query.
        score = body_overlap + title_overlap * 2
        if score:
            scored.append((score, path))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [path for _score, path in scored[:limit]]


def evaluate(
    entries: list[dict], documents: dict[str, str], limit: int = 5
) -> list[dict]:
    failures = []
    for entry in entries:
        retrieved = rank_documents(str(entry.get("query", "")), documents, limit)
        evidence = entry.get("evidence") or []
        if not any(path in retrieved for path in evidence):
            failures.append(
                {
                    "id": entry.get("id"),
                    "evidence": evidence,
                    "retrieved": retrieved,
                }
            )
    return failures


def load_documents(root: Path) -> dict[str, str]:
    documents = {}
    for path in sorted(root.rglob("*.md")):
        if path.name == "index.md":
            continue
        rel = "/" + str(path.relative_to(root))
        documents[rel] = path.read_text(encoding="utf-8")
    return documents


# ---------------------------------------------------------------------------
# kb eval summary / smoke の結果組み立て
# ---------------------------------------------------------------------------


def eval_file(repo_root: Path) -> Path:
    return repo_root / DEFAULT_EVAL_FILE


def list_assets(repo_root: Path) -> list[str]:
    """evals/ 配下のファイル一覧（情報表示用）。"""
    root = repo_root / "evals"
    if not root.is_dir():
        return []
    return sorted(str(p.relative_to(repo_root)) for p in root.rglob("*") if p.is_file())


def _missing(repo_root: Path) -> dict[str, Any]:
    return {
        "ok": False,
        "assets": list_assets(repo_root),
        "diagnostics": [{"code": "eval.assets.missing", "message": f"no local evaluation assets found ({DEFAULT_EVAL_FILE})"}],
    }


def summary_result(repo_root: Path) -> dict[str, Any]:
    """最新判定の集計・退行・未解決欠落を返す。退行があれば ok は False。"""
    path = eval_file(repo_root)
    if not path.is_file():
        return _missing(repo_root)
    entries = load_entries(path)
    latest = summarize_latest(entries)
    regressions = find_regressions(entries)
    # スキーマ検査は kb validate（_validate_evals）の責務。ここは集計と退行だけを見る
    diagnostics = [
        {
            "code": "eval.regression",
            "message": f"REGRESSION {r['id']}: {r['last_ok_date']} OK → {r['latest_date']} {r['latest_verdict']}",
        }
        for r in regressions
    ]
    return {
        "ok": not diagnostics,
        "assets": list_assets(repo_root),
        "diagnostics": diagnostics,
        "summary": {
            "evaluated": latest["evaluated"],
            "total": latest["total"],
            "by_verdict": {k: v for k, v in sorted(latest["by_verdict"].items()) if v},
            "by_kind": latest["by_kind"],
        },
        "regressions": regressions,
        "open_gaps": sorted(find_open_gaps(entries), key=lambda item: str(item.get("id", ""))),
    }


def smoke_result(repo_root: Path, content_root: Path, *, limit: int = 5) -> dict[str, Any]:
    """期待根拠が字面検索の上位 limit 件に入るかを検査する。外れがあれば ok は False。"""
    path = eval_file(repo_root)
    if not path.is_file():
        return _missing(repo_root)
    entries = load_entries(path)
    documents = load_documents(content_root)
    # history が空のエントリは計画のみで未評価。スモークの対象にしない
    targets = [entry for entry in entries if entry.get("history")]
    failures = evaluate(targets, documents, limit)
    return {
        "ok": not failures,
        "assets": list_assets(repo_root),
        "diagnostics": [
            {"code": "eval.smoke.miss", "message": f"MISS {f['id']}: expected={f['evidence']} retrieved={f['retrieved']}"}
            for f in failures
        ],
        "evaluated": len(targets),
        "limit": limit,
        "failures": failures,
    }
