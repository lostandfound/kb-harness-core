"""型ごとの sources_required: false で出典を省略できることを確認する。"""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from kb_harness.cli import main
from kb_harness.validation import validate

VOCAB = (
    "types:\n"
    "  Note:\n"
    "    directory: notes\n"
    "    sources_required: false\n"
    "  Person:\n"
    "    directory: people\n"
    "predicates: {}\n"
    "tags: [index, misc]\n"
)
INDEX = (
    "---\ntype: Index\ntitle: {title}\ndescription: list.\n"
    "tags: [index]\ntimestamp: 2026-09-01T00:00:00Z\n---\n\n# {title}\n\n## エンティティ一覧\n\n"
)


def _entity(type_name: str, sources: str | None) -> str:
    fm = f"---\ntype: {type_name}\ntitle: 例\ndescription: 例。\ntags: [misc]\n"
    if sources is not None:
        fm += f"sources: {sources}\n"
    fm += "timestamp: 2026-09-01T00:00:00Z\n---\n\n# 例\n\n## 概要\n\n本文。\n"
    return fm


class SourcesOptionalTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        content = self.root / "knowledge"
        for d in ("notes", "people"):
            (content / d).mkdir(parents=True)
            (content / d / "index.md").write_text(INDEX.format(title=d), encoding="utf-8")
        (self.root / "kb-domain.yml").write_text("domain:\n  content_root: knowledge\n", encoding="utf-8")
        (content / "vocabulary.yml").write_text(VOCAB, encoding="utf-8")
        self.content = content

    def tearDown(self):
        self.tmp.cleanup()

    def test_validate_accepts_missing_sources_when_type_opts_out(self):
        (self.content / "notes" / "memo.md").write_text(_entity("Note", None), encoding="utf-8")
        errors = validate(self.content)
        self.assertEqual([e for e in errors if "sources" in e], [])

    def test_validate_still_requires_sources_by_default(self):
        (self.content / "people" / "someone.md").write_text(_entity("Person", None), encoding="utf-8")
        errors = validate(self.content)
        self.assertTrue(any("missing required field 'sources'" in e for e in errors))

    def test_entity_create_accepts_spec_without_sources_when_type_opts_out(self):
        (self.root / "entity.yml").write_text(
            "type: Note\nslug: memo\ntitle: メモ\ndescription: メモ。\ntags: [misc]\n"
            "sections:\n  概要: |\n    本文。\n  本文: |\n    本文。\n  関連項目: |\n    なし。\n",
            encoding="utf-8",
        )
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["entity", "create", "--from", str(self.root / "entity.yml"),
                         "--timestamp", "2026-09-01T00:00:00Z", "--start", str(self.root), "--format", "json"])
        self.assertEqual(code, 0, err.getvalue() + out.getvalue())
        self.assertTrue(json.loads(out.getvalue())["ok"])
        self.assertNotIn("sources", (self.content / "notes" / "memo.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
