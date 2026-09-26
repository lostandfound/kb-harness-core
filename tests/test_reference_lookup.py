"""``kb reference show`` / ``kb reference search``: レジストリを丸ごと読まずに必要な項目だけ引く。"""
from __future__ import annotations

import json
from pathlib import Path

from kb_harness.cli import main
from kb_harness.references import (
    entity_reference_ids,
    normalize_doi,
    normalize_url,
    reference_search,
    reference_show,
)

REGISTRY = """\
# コメントは保持されなくてよい（読み取り専用）
smith-2001:
  type: book
  author: Alice Smith
  title: Karate History
  publisher: Example Press
  year: 2001
  url: https://www.example.test/karate/
  note: 空手の通史
wikipedia-ja-karate:
  type: web
  author: Wikipedia 日本語版
  title: 空手道
  url: https://ja.wikipedia.org/wiki/空手道
  note: 概要と流派
doe-2020:
  type: journal-article
  author: Jane Doe
  title: Bowing Etiquette
  doi: 10.1000/example.2020
  year: 2020
"""


def _project(tmp_path: Path) -> Path:
    content = tmp_path / "content"
    (content / "people").mkdir(parents=True)
    (tmp_path / "kb-domain.yml").write_text("domain:\n  content_root: content\n", encoding="utf-8")
    (content / "references.yml").write_text(REGISTRY, encoding="utf-8")
    (content / "people" / "alice.md").write_text(
        "---\n"
        "type: Person\n"
        "title: アリス\n"
        "sources:\n"
        '  - "ref: smith-2001"\n'
        '  - "https://example.test/direct"\n'
        "---\n"
        "## 概要\n\n"
        "礼法は文献に詳しい（出典: doe-2020, ref: smith-2001）。\n",
        encoding="utf-8",
    )
    return tmp_path


def _run(root: Path, *argv: str, fmt: str = "json") -> tuple[int, str, str]:
    import io
    import contextlib

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main([*argv, "--start", str(root), "--format", fmt])
    return code, out.getvalue(), err.getvalue()


# --- API ---------------------------------------------------------------------


def test_show_returns_entries_in_requested_order_and_reports_missing(tmp_path: Path):
    root = _project(tmp_path)
    result = reference_show(root / "content" / "references.yml", ["doe-2020", "nope", "smith-2001"])
    assert [e["id"] for e in result["entries"]] == ["doe-2020", "smith-2001"]
    assert result["missing"] == ["nope"]
    assert result["ok"] is False
    assert result["diagnostics"][0]["code"] == "reference.id.missing"


def test_entity_reference_ids_merges_sources_and_inline_citations_in_first_seen_order(tmp_path: Path):
    root = _project(tmp_path)
    ids = entity_reference_ids(root / "content" / "people" / "alice.md")
    assert ids == ["smith-2001", "doe-2020"]


def test_search_terms_are_case_insensitive_and_anded(tmp_path: Path):
    root = _project(tmp_path)
    registry = root / "content" / "references.yml"
    assert [e["id"] for e in reference_search(registry, ["karate"])["entries"]] == ["smith-2001", "wikipedia-ja-karate"]
    assert [e["id"] for e in reference_search(registry, ["KARATE", "smith"])["entries"]] == ["smith-2001"]
    assert [e["id"] for e in reference_search(registry, ["空手"])["entries"]] == ["smith-2001", "wikipedia-ja-karate"]


def test_search_field_restriction_and_limit(tmp_path: Path):
    root = _project(tmp_path)
    registry = root / "content" / "references.yml"
    assert [e["id"] for e in reference_search(registry, ["空手"], fields=("title",))["entries"]] == ["wikipedia-ja-karate"]
    result = reference_search(registry, ["e"], limit=1)
    assert result["count"] == 3 and result["shown"] == 1


def test_search_by_normalized_url_and_doi(tmp_path: Path):
    root = _project(tmp_path)
    registry = root / "content" / "references.yml"
    hits = reference_search(registry, [], url="http://example.test/karate#top")["entries"]
    assert [e["id"] for e in hits] == ["smith-2001"]
    hits = reference_search(registry, [], doi="https://doi.org/10.1000/EXAMPLE.2020")["entries"]
    assert [e["id"] for e in hits] == ["doe-2020"]
    assert reference_search(registry, ["karate"], url="https://example.test/karate", doi="10.1000/x")["entries"] == []


def test_normalizers():
    assert normalize_url("HTTPS://www.Example.test/a/b/#frag") == "example.test/a/b"
    assert normalize_doi("doi: 10.1000/ABC") == "10.1000/abc"
    assert normalize_doi("https://dx.doi.org/10.1000/abc") == "10.1000/abc"


# --- CLI ---------------------------------------------------------------------


def test_cli_show_by_id_text_and_json(tmp_path: Path):
    root = _project(tmp_path)
    code, out, err = _run(root, "reference", "show", "smith-2001")
    assert code == 0
    payload = json.loads(out)
    assert payload["ok"] is True and payload["entries"][0]["title"] == "Karate History"
    code, out, _ = _run(root, "reference", "show", "smith-2001", fmt="text")
    assert code == 0 and out.startswith("smith-2001:\n") and "Karate History" in out


def test_cli_show_missing_id_exits_1(tmp_path: Path):
    root = _project(tmp_path)
    code, out, err = _run(root, "reference", "show", "smith-2001", "nope")
    assert code == 1
    payload = json.loads(out)
    assert payload["missing"] == ["nope"] and len(payload["entries"]) == 1


def test_cli_show_for_entity(tmp_path: Path):
    root = _project(tmp_path)
    code, out, _ = _run(root, "reference", "show", "--for", str(root / "content" / "people" / "alice.md"))
    assert code == 0
    payload = json.loads(out)
    assert payload["ids"] == ["smith-2001", "doe-2020"]
    assert [e["id"] for e in payload["entries"]] == ["smith-2001", "doe-2020"]


def test_cli_show_requires_ids_or_entity(tmp_path: Path):
    root = _project(tmp_path)
    code, _, err = _run(root, "reference", "show")
    assert code == 2 and json.loads(err)["diagnostics"][0]["code"] == "reference.show.arguments"
    code, _, err = _run(root, "reference", "show", "smith-2001", "--for", "x.md")
    assert code == 2


def test_cli_search_text_prints_one_line_per_hit(tmp_path: Path):
    root = _project(tmp_path)
    code, out, err = _run(root, "reference", "search", "karate", fmt="text")
    assert code == 0
    lines = out.splitlines()
    assert lines[0].startswith("smith-2001\tbook\tKarate History\tAlice Smith\t2001\t")
    assert len(lines) == 2 and "count: 2" in err


def test_cli_search_url_dedupe_and_no_args(tmp_path: Path):
    root = _project(tmp_path)
    code, out, _ = _run(root, "reference", "search", "--url", "http://example.test/karate")
    assert code == 0 and [e["id"] for e in json.loads(out)["entries"]] == ["smith-2001"]
    code, _, err = _run(root, "reference", "search")
    assert code == 2 and json.loads(err)["diagnostics"][0]["code"] == "reference.search.arguments"


def test_cli_search_empty_registry(tmp_path: Path):
    root = _project(tmp_path)
    (root / "content" / "references.yml").write_text("{}\n", encoding="utf-8")
    code, out, _ = _run(root, "reference", "search", "anything")
    assert code == 0 and json.loads(out)["count"] == 0
