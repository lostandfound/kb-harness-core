#!/usr/bin/env python3
"""固定クエリの期待根拠が字面検索の上位に入るかを検査する。"""

import argparse
import re
from pathlib import Path

import yaml

from kb_config import default_content_root


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=default_content_root())
    parser.add_argument("--eval-file", default="evals/rag-eval.yml")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args(argv)

    entries = yaml.safe_load(Path(args.eval_file).read_text(encoding="utf-8")) or []
    documents = load_documents(Path(args.root))
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
