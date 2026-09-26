"""本文リンクは相対パスで書き、旧形式のルート相対リンクは移行できることを確認する。"""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from kb_harness.cli import main
from kb_harness.links import relativize_body, resolve_link, rootify_body
from kb_harness.validation import validate

VOCAB = (
    "types:\n"
    "  Note:\n"
    "    directory: notes\n"
    "    sources_required: false\n"
    "  Person:\n"
    "    directory: people\n"
    "    sources_required: false\n"
    "predicates: {}\n"
    "tags: [index, misc]\n"
)
HEADER = "---\ntype: {type}\ntitle: {title}\ndescription: {title}の説明。\ntags: [{tag}]\ntimestamp: 2026-09-01T00:00:00Z\n---\n\n"


def _doc(type_name: str, title: str, body: str, tag: str = "misc") -> str:
    return HEADER.format(type=type_name, title=title, tag=tag) + body


class ResolveLinkTest(unittest.TestCase):
    def test_resolves_relative_and_root_relative_links_to_ids(self):
        self.assertEqual(resolve_link("/notes/a.md", "b.md"), "/notes/b.md")
        self.assertEqual(resolve_link("/notes/a.md", "./b.md"), "/notes/b.md")
        self.assertEqual(resolve_link("/notes/a.md", "../people/p.md"), "/people/p.md")
        self.assertEqual(resolve_link("/index.md", "notes/index.md"), "/notes/index.md")
        self.assertEqual(resolve_link("/notes/a.md", "/people/p.md"), "/people/p.md")

    def test_link_escaping_content_root_is_unresolved(self):
        self.assertIsNone(resolve_link("/notes/a.md", "../../README.md"))

    def test_relativize_rewrites_only_root_relative_links(self):
        body = (
            "[P](/people/p.md) [B](/notes/b.md#経歴) [R](../people/p.md) "
            "[U](https://example.com/x.md) [N](//example.com/x.md)"
        )
        self.assertEqual(
            relativize_body("/notes/a.md", body),
            "[P](../people/p.md) [B](b.md#経歴) [R](../people/p.md) "
            "[U](https://example.com/x.md) [N](//example.com/x.md)",
        )
        self.assertEqual(relativize_body("/index.md", "[N](/notes/index.md)"), "[N](notes/index.md)")

    def test_rootify_turns_relative_links_into_ids(self):
        body = "[P](../people/p.md) [B](b.md#経歴) [X](../../README.md) [U](https://example.com/x.md)"
        self.assertEqual(
            rootify_body("/notes/a.md", body),
            "[P](/people/p.md) [B](/notes/b.md) [X](../../README.md) [U](https://example.com/x.md)",
        )


class LinkValidationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.content = self.root / "knowledge"
        for directory in ("notes", "people"):
            (self.content / directory).mkdir(parents=True)
        (self.root / "kb-domain.yml").write_text("domain:\n  content_root: knowledge\n", encoding="utf-8")
        (self.root / "README.md").write_text("# readme\n", encoding="utf-8")
        (self.content / "vocabulary.yml").write_text(VOCAB, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _write_kb(self, *, root_relative: bool) -> None:
        def href(source: str, target: str) -> str:
            return target if root_relative else {
                ("/index.md", "/notes/index.md"): "notes/index.md",
                ("/index.md", "/people/index.md"): "people/index.md",
                ("/notes/index.md", "/notes/memo.md"): "memo.md",
                ("/people/index.md", "/people/someone.md"): "someone.md",
                ("/notes/memo.md", "/people/someone.md"): "../people/someone.md",
            }[(source, target)]

        (self.content / "index.md").write_text(
            _doc("Index", "Root", f"- [Notes]({href('/index.md', '/notes/index.md')})\n"
                 f"- [People]({href('/index.md', '/people/index.md')})\n", tag="index"),
            encoding="utf-8",
        )
        (self.content / "notes" / "index.md").write_text(
            _doc("Index", "Notes", f"- [メモ]({href('/notes/index.md', '/notes/memo.md')})\n", tag="index"),
            encoding="utf-8",
        )
        (self.content / "people" / "index.md").write_text(
            _doc("Index", "People", f"- [誰か]({href('/people/index.md', '/people/someone.md')})\n", tag="index"),
            encoding="utf-8",
        )
        (self.content / "notes" / "memo.md").write_text(
            _doc("Note", "メモ", f"[誰か]({href('/notes/memo.md', '/people/someone.md')})と[README](../../README.md)。\n"),
            encoding="utf-8",
        )
        (self.content / "people" / "someone.md").write_text(_doc("Person", "誰か", "本文。\n"), encoding="utf-8")

    def _link_errors(self, errors: list[str]) -> list[str]:
        return [e for e in errors if "link" in e or "index" in e]

    def test_relative_links_pass_including_index_coverage(self):
        self._write_kb(root_relative=False)
        warnings: list[str] = []
        errors = validate(self.content, warnings)
        self.assertEqual(self._link_errors(errors), [])
        self.assertNotIn("validation.link.root_relative", [getattr(w, "code", "") for w in warnings])

    def test_broken_relative_link_is_reported(self):
        self._write_kb(root_relative=False)
        (self.content / "notes" / "memo.md").write_text(
            _doc("Note", "メモ", "[無い](../people/nobody.md)と[外](../../missing.md)。\n"), encoding="utf-8"
        )
        errors = validate(self.content)
        self.assertIn("ERROR /notes/memo.md: broken link '../people/nobody.md'", errors)
        self.assertIn("ERROR /notes/memo.md: broken link '../../missing.md'", errors)

    def test_index_missing_entity_link_uses_resolved_links(self):
        self._write_kb(root_relative=False)
        (self.content / "notes" / "index.md").write_text(_doc("Index", "Notes", "なし\n", tag="index"), encoding="utf-8")
        errors = validate(self.content)
        self.assertIn("ERROR /notes/index.md: index missing entity link '/notes/memo.md'", errors)

    def test_root_relative_links_still_resolve_but_warn(self):
        self._write_kb(root_relative=True)
        warnings: list[str] = []
        errors = validate(self.content, warnings)
        self.assertEqual(self._link_errors(errors), [])
        codes = [getattr(w, "code", "") for w in warnings]
        self.assertEqual(codes.count("validation.link.root_relative"), 1)

    def test_link_migrate_check_then_write(self):
        self._write_kb(root_relative=True)
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(["link", "migrate", "--check", "--start", str(self.root), "--format", "json"])
        result = json.loads(output.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertEqual({d["code"] for d in result["diagnostics"]}, {"link.root_relative"})
        self.assertIn("knowledge/notes/memo.md", [d["path"] for d in result["diagnostics"]])

        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["link", "migrate", "--start", str(self.root), "--format", "json"]), 0)
        memo = (self.content / "notes" / "memo.md").read_text(encoding="utf-8")
        self.assertIn("[誰か](../people/someone.md)", memo)
        self.assertIn("[Notes](notes/index.md)", (self.content / "index.md").read_text(encoding="utf-8"))

        warnings: list[str] = []
        self.assertEqual(self._link_errors(validate(self.content, warnings)), [])
        self.assertNotIn("validation.link.root_relative", [getattr(w, "code", "") for w in warnings])
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["link", "migrate", "--check", "--start", str(self.root), "--format", "json"]), 0)


if __name__ == "__main__":
    unittest.main()
