"""--check-urls の対象の絞り込み（--for / --ref）、重複除去、並列化後の出力順。

判断の経緯は docs/notes/url-kakunin-memo.md。
"""

import io
import json
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from kb_harness.cli import main
from kb_harness.validation import check_urls


def _kb(tempdir):
    root = Path(tempdir)
    content = root / "knowledge"
    notes = content / "notes"
    notes.mkdir(parents=True)
    (root / "kb-domain.yml").write_text("domain:\n  content_root: knowledge\n", encoding="utf-8")
    (content / "vocabulary.yml").write_text(
        "types:\n  Note:\n    directory: notes\n    graph: false\n"
        "predicates: {}\ntags: []\n",
        encoding="utf-8",
    )
    (content / "references.yml").write_text(
        "ref-a:\n  type: web\n  title: A\n  url: https://a.example/a\n"
        "ref-b:\n  type: web\n  title: B\n  url: https://b.example/b\n"
        "ref-c:\n  type: web\n  title: C\n  url: https://c.example/c\n"
        "ref-d:\n  type: paper\n  author: D\n  title: D\n  doi: 10.1000/d\n",
        encoding="utf-8",
    )
    (notes / "one.md").write_text(
        "---\ntype: Note\ntitle: one\ndescription: One.\ntags: []\ntimestamp: 2026-01-01T00:00:00Z\n"
        "sources:\n  - 'ref: ref-a'\n  - https://direct.example/one\n---\n\n"
        "## 概要\n\n本文（出典: ref-b）\n",
        encoding="utf-8",
    )
    (notes / "two.md").write_text(
        "---\ntype: Note\ntitle: two\ndescription: Two.\ntags: []\ntimestamp: 2026-01-01T00:00:00Z\n"
        "sources:\n  - 'ref: ref-c'\n  - https://direct.example/one\n---\n\nBody\n",
        encoding="utf-8",
    )
    return root, content


class CheckUrlsScopeTest(unittest.TestCase):
    def test_指定がなければKB全体を確かめ同じURLは1回だけ確かめる(self):
        with tempfile.TemporaryDirectory() as tempdir:
            _root, content = _kb(tempdir)
            with patch("kb_harness.validation._url_reachable", return_value=True) as reachable, patch(
                "kb_harness.validation._doi_registered", return_value=True
            ) as registered:
                self.assertEqual(check_urls(content), [])
            checked = sorted(call.args[0] for call in reachable.call_args_list)
            self.assertEqual(
                checked,
                ["https://a.example/a", "https://b.example/b", "https://c.example/c", "https://direct.example/one"],
            )
            registered.assert_called_once_with("10.1000/d")

    def test_forはエンティティのsourcesと本文の出典だけを確かめる(self):
        with tempfile.TemporaryDirectory() as tempdir:
            _root, content = _kb(tempdir)
            with patch("kb_harness.validation._url_reachable", return_value=True) as reachable, patch(
                "kb_harness.validation._doi_registered", return_value=True
            ) as registered:
                self.assertEqual(check_urls(content, entities=[content / "notes" / "one.md"]), [])
            checked = sorted(call.args[0] for call in reachable.call_args_list)
            self.assertEqual(checked, ["https://a.example/a", "https://b.example/b", "https://direct.example/one"])
            registered.assert_not_called()

    def test_refは指定した出典だけを確かめる(self):
        with tempfile.TemporaryDirectory() as tempdir:
            _root, content = _kb(tempdir)
            with patch("kb_harness.validation._url_reachable", return_value=True) as reachable, patch(
                "kb_harness.validation._doi_registered", return_value=False
            ):
                errors = check_urls(content, ref_ids=["ref-c", "ref-d"])
            reachable.assert_called_once_with("https://c.example/c")
            self.assertEqual(errors, ["ERROR /references.yml: DOI unregistered 10.1000/d (ref-d)"])

    def test_見つからないエンティティと出典IDはERROR(self):
        with tempfile.TemporaryDirectory() as tempdir:
            _root, content = _kb(tempdir)
            with patch("kb_harness.validation._url_reachable", return_value=True) as reachable:
                errors = check_urls(content, entities=[content / "notes" / "missing.md"], ref_ids=["nope"])
            reachable.assert_not_called()
            self.assertEqual(
                errors,
                [
                    "ERROR /notes/missing.md: entity not found",
                    "ERROR /references.yml: reference id not found (nope)",
                ],
            )

    def test_並列に確かめてもERRORの並びは走査順(self):
        with tempfile.TemporaryDirectory() as tempdir:
            _root, content = _kb(tempdir)
            active = 0
            peak = 0
            lock = threading.Lock()

            def slow_unreachable(url):
                nonlocal active, peak
                with lock:
                    active += 1
                    peak = max(peak, active)
                # 先に走査した URL ほど遅く返し、完了順と走査順をずらす
                time.sleep({"https://a.example/a": 0.2, "https://b.example/b": 0.1}.get(url, 0.0))
                with lock:
                    active -= 1
                return False

            with patch("kb_harness.validation._url_reachable", side_effect=slow_unreachable):
                errors = check_urls(content, ref_ids=["ref-a", "ref-b", "ref-c"])
            self.assertEqual(
                errors,
                [
                    "ERROR /references.yml: unreachable URL https://a.example/a (ref-a)",
                    "ERROR /references.yml: unreachable URL https://b.example/b (ref-b)",
                    "ERROR /references.yml: unreachable URL https://c.example/c (ref-c)",
                ],
            )
            self.assertGreater(peak, 1)

    def test_同じホストへの同時接続は上限までに抑える(self):
        with tempfile.TemporaryDirectory() as tempdir:
            content = Path(tempdir) / "knowledge"
            content.mkdir()
            (content / "references.yml").write_text(
                "".join(
                    f"r{i}:\n  type: web\n  title: R{i}\n  url: https://same.example/{i}\n" for i in range(6)
                ),
                encoding="utf-8",
            )
            active = 0
            peak = 0
            lock = threading.Lock()

            def slow(url):
                nonlocal active, peak
                with lock:
                    active += 1
                    peak = max(peak, active)
                time.sleep(0.05)
                with lock:
                    active -= 1
                return True

            with patch("kb_harness.validation._url_reachable", side_effect=slow):
                self.assertEqual(check_urls(content), [])
            self.assertLessEqual(peak, 2)


class ValidateCliScopeTest(unittest.TestCase):
    def test_forとrefをCLIから渡せる(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root, content = _kb(tempdir)
            output = io.StringIO()
            with patch("kb_harness.validation._url_reachable", return_value=True) as reachable:
                with redirect_stdout(output):
                    exit_code = main(
                        [
                            "validate", "--check-urls",
                            "--for", str(content / "notes" / "two.md"),
                            "--ref", "ref-a",
                            "--start", str(root), "--format", "json",
                        ]
                    )
            result = json.loads(output.getvalue())
            self.assertEqual(result["diagnostics"], [])
            self.assertEqual(exit_code, 0)
            checked = sorted(call.args[0] for call in reachable.call_args_list)
            self.assertEqual(checked, ["https://a.example/a", "https://c.example/c", "https://direct.example/one"])

    def test_check_urlsなしのforは引数の誤り(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root, content = _kb(tempdir)
            output = io.StringIO()
            with redirect_stdout(output), redirect_stderr(io.StringIO()):
                exit_code = main(
                    ["validate", "--for", str(content / "notes" / "one.md"), "--start", str(root), "--format", "json"]
                )
            self.assertEqual(exit_code, 2)
            self.assertEqual(json.loads(output.getvalue())["diagnostics"][0]["code"], "validation.arguments")


if __name__ == "__main__":
    unittest.main()
