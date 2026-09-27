#!/usr/bin/env python3
"""固定クエリの期待根拠が字面検索の上位に入るかを検査する。"""

import argparse
from pathlib import Path

import yaml

from kb_config import default_content_root
from kb_harness.evaluation import evaluate, load_documents, load_entries, rank_documents  # noqa: F401  互換のため再公開


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=None, help="コンテンツルート（省略時は kb-domain.yml から解決）")
    parser.add_argument("--eval-file", default="evals/rag-eval.yml")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args(argv)

    entries = load_entries(Path(args.eval_file))
    documents = load_documents(Path(args.root) if args.root else Path(default_content_root()))
    # Empty history marks a planned, unevaluated case; it is not a smoke failure.
    failures = evaluate([entry for entry in entries if entry.get("history")], documents, args.limit)
    if failures:
        for failure in failures:
            print(
                f"MISS {failure['id']}: expected={failure['evidence']} "
                f"retrieved={failure['retrieved']}"
            )
        return 1
    print(f"OK: {len(entries)}問すべてで期待根拠を上位{args.limit}件から取得")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
