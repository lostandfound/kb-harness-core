"""BACKLOG R3: validate の取りこぼし 3 件に対する回帰テスト。

(a) content_root 直下の index.md 以外の .md が検査を素通りする
(b) directory を欠く型がルート index に '/None/index.md' を要求する
(c) evals/ の探索が content_root.parent に固定され、content_root がリポジトリ
    ルート直下に無い配置（kb-domain.yml の domain.content_root: kb/entities 等）で
    黙ってスキップされる
"""
from __future__ import annotations

from pathlib import Path

from kb_harness.validation import validate

VOCAB = (
    "types:\n  Person:\n    directory: people\npredicates: {}\ntags: []\n"
)

ROOT_INDEX = (
    "---\ntype: Index\ntitle: root\ndescription: d\ntags: []\n"
    "timestamp: 2024-01-01T00:00:00Z\n---\n- [people](people/index.md)\n"
)

PEOPLE_INDEX = (
    "---\ntype: Index\ntitle: people\ndescription: d\ntags: []\n"
    "timestamp: 2024-01-01T00:00:00Z\n---\n- [taro](taro.md)\n"
)

PERSON = (
    "---\ntype: Person\ntitle: 太郎\ndescription: 説明\ntags: []\n"
    "sources: [https://example.test]\ntimestamp: 2024-01-01T00:00:00Z\n---\n本文\n"
)


def _minimal_kb(root: Path) -> Path:
    content = root / "content"
    (content / "people").mkdir(parents=True)
    (content / "vocabulary.yml").write_text(VOCAB, encoding="utf-8")
    (content / "index.md").write_text(ROOT_INDEX, encoding="utf-8")
    (content / "people" / "index.md").write_text(PEOPLE_INDEX, encoding="utf-8")
    (content / "people" / "taro.md").write_text(PERSON, encoding="utf-8")
    return content


# --- (a) content_root 直下の迷子 .md ---------------------------------------


def test_stray_markdown_directly_under_content_root_is_an_error(tmp_path: Path):
    content = _minimal_kb(tmp_path)
    (content / "stray.md").write_text(PERSON, encoding="utf-8")

    errors = validate(content)

    assert any("/stray.md" in e and "content_root 直下" in e for e in errors), errors


def test_index_md_directly_under_content_root_is_not_flagged(tmp_path: Path):
    content = _minimal_kb(tmp_path)

    errors = validate(content)

    assert not any("content_root 直下" in e for e in errors), errors


# --- (b) directory を欠く型 --------------------------------------------------


def test_type_missing_directory_is_reported_and_excluded_from_root_index_requirement(tmp_path: Path):
    content = _minimal_kb(tmp_path)
    (content / "vocabulary.yml").write_text(
        "types:\n  Person:\n    directory: people\n  Note:\n    sources_required: false\n"
        "predicates: {}\ntags: []\n",
        encoding="utf-8",
    )

    errors = validate(content)

    assert any("types.Note.directory" in e for e in errors), errors
    # '/None/index.md' を要求してはならない
    assert not any("None" in e for e in errors), errors


# --- (c) evals の探索は repo_root であって content_root.parent ではない ------


def test_evals_are_found_via_repo_root_even_when_content_root_is_nested(tmp_path: Path):
    # domain.content_root: kb/entities のような配置。content_root.parent (= tmp_path/kb) は
    # リポジトリルート (= tmp_path) ではない
    nested_root = tmp_path / "kb"
    content = nested_root / "entities"
    (content / "people").mkdir(parents=True)
    (content / "vocabulary.yml").write_text(VOCAB, encoding="utf-8")
    (content / "index.md").write_text(ROOT_INDEX, encoding="utf-8")
    (content / "people" / "index.md").write_text(PEOPLE_INDEX, encoding="utf-8")
    (content / "people" / "taro.md").write_text(PERSON, encoding="utf-8")

    evals_dir = tmp_path / "evals"
    evals_dir.mkdir()
    (evals_dir / "rag-eval.yml").write_text(
        "- id: q1\n  query: q\n  expected: x\n  evidence: [/does-not-exist.md]\n",
        encoding="utf-8",
    )

    # repo_root を渡さない従来の呼び方は content_root.parent (tmp_path/kb) しか見ないので、
    # tmp_path/evals は見つからず検査もスキップされる
    errors_without_repo_root = validate(content)
    assert not any("evals/rag-eval.yml" in e for e in errors_without_repo_root), errors_without_repo_root

    # repo_root を渡すと、リポジトリルート直下の evals/ を正しく見つけて検証する
    errors_with_repo_root = validate(content, repo_root=tmp_path)
    assert any(
        "evals/rag-eval.yml" in e and "does-not-exist.md" in e for e in errors_with_repo_root
    ), errors_with_repo_root
