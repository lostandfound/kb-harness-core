#!/usr/bin/env python3
"""RAG 評価データセット（evals/rag-eval.yml）の決定論集計・退行検出。

test-rag スキルが history を追記した後、目視だけでは退行（過去 OK → 最新非 OK）を
見落としうるため、機械判定を挟んで CI・運用ループに組み込めるようにする。
"""
import argparse
import sys
from pathlib import Path

from kb_config import default_content_root
from kb_harness.evaluation import (  # noqa: F401  互換のため再公開
    DEFAULT_EVAL_FILE,
    GAP_KINDS,
    REQUIRED_FIELDS,
    VERDICTS,
    filter_history_since,
    find_open_gaps,
    find_regressions,
    find_stale,
    format_open_lines,
    format_report,
    latest_record,
    load_entries,
    summarize_latest,
    validate_entries,
)


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
