"""R6(d): `_validate_evals` / `fix_timestamps` / `_url_reachable` の未検証経路を塞ぐ。"""

import io
import subprocess
import unittest
import urllib.error
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from kb_harness.diagnostics import HarnessError
from kb_harness.validation import _url_reachable, _validate_evals, fix_timestamps


def _response(status: int):
    body = io.BytesIO(b"")
    body.status = status
    body.__enter__ = lambda self=body: self
    body.__exit__ = lambda *args: False
    return body


class ValidateEvalsTest(unittest.TestCase):
    def test_evalsファイルが無ければ空(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "knowledge"
            root.mkdir()
            self.assertEqual(_validate_evals(root, set()), [])

    def test_entriesがlist以外ならエラー(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "knowledge"
            root.mkdir()
            evals = Path(tmp) / "evals"
            evals.mkdir()
            (evals / "rag-eval.yml").write_text("entries: {}\n", encoding="utf-8")
            errors = _validate_evals(root, set())
            self.assertEqual(len(errors), 1)
            self.assertIn("must be a list", errors[0])

    def test_空listは有効(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "knowledge"
            root.mkdir()
            evals = Path(tmp) / "evals"
            evals.mkdir()
            (evals / "rag-eval.yml").write_text("[]\n", encoding="utf-8")
            self.assertEqual(_validate_evals(root, set()), [])

    def test_id欠落と重複と必須フィールド欠落を検出する(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "knowledge"
            root.mkdir()
            evals = Path(tmp) / "evals"
            evals.mkdir()
            (evals / "rag-eval.yml").write_text(
                "- id: a\n"
                "  query: q\n"
                "  expected: e\n"
                "  evidence: [/notes/a.md]\n"
                "- id: a\n"
                "  query: q2\n"
                "  expected: e2\n"
                "  evidence: [/notes/a.md]\n"
                "- query: q3\n",
                encoding="utf-8",
            )
            errors = _validate_evals(root, {"/notes/a.md"})
            self.assertTrue(any("重複している" in e for e in errors))
            self.assertTrue(any("missing required field 'id'" in e for e in errors))

    def test_evidenceがバンドル外なら検出する(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "knowledge"
            root.mkdir()
            evals = Path(tmp) / "evals"
            evals.mkdir()
            (evals / "rag-eval.yml").write_text(
                "- id: a\n  query: q\n  expected: e\n  evidence: [/notes/missing.md]\n",
                encoding="utf-8",
            )
            errors = _validate_evals(root, {"/notes/a.md"})
            self.assertTrue(any("バンドルに存在しない" in e for e in errors))


class FixTimestampsTest(unittest.TestCase):
    def test_git管理外ではCalledProcessErrorを漏らさずHarnessErrorにする(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(HarnessError) as ctx:
                fix_timestamps(root)
            self.assertEqual(ctx.exception.diagnostic.code, "validation.timestamps.git_required")
            self.assertNotIsInstance(ctx.exception, subprocess.CalledProcessError)

    def test_git管理下では変更されたmdのtimestampを書き換える(self):
        with TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.email", "a@example.com"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "a"], cwd=repo, check=True)
            target = repo / "note.md"
            target.write_text("---\ntimestamp: 2000-01-01T00:00:00Z\n---\nBody\n", encoding="utf-8")
            subprocess.run(["git", "add", "note.md"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)
            target.write_text("---\ntimestamp: 2000-01-01T00:00:00Z\n---\nBody changed\n", encoding="utf-8")

            fixed = fix_timestamps(repo)

            self.assertEqual(fixed, [target.resolve()])
            self.assertNotIn("2000-01-01T00:00:00Z", target.read_text(encoding="utf-8"))


class UrlReachableTest(unittest.TestCase):
    def test_HEADが200なら到達可能(self):
        with patch("urllib.request.urlopen", return_value=_response(200)) as opened:
            self.assertTrue(_url_reachable("https://example.com/a"))
        self.assertEqual(opened.call_count, 1)

    def test_HEADが404ならGETにフォールバックせず到達不能(self):
        def raise_404(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)

        with patch("urllib.request.urlopen", side_effect=raise_404) as opened:
            self.assertFalse(_url_reachable("https://example.com/missing"))
        self.assertEqual(opened.call_count, 1)

    def test_HEADが403ならGETにフォールバックして到達可能を判定する(self):
        def side_effect(req, timeout=None):
            if req.get_method() == "HEAD":
                raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)
            self.assertEqual(req.get_method(), "GET")
            return _response(200)

        with patch("urllib.request.urlopen", side_effect=side_effect) as opened:
            self.assertTrue(_url_reachable("https://example.com/bot-blocked"))
        self.assertEqual(opened.call_count, 2)

    def test_HEADが405でGETも失敗すれば到達不能(self):
        def side_effect(req, timeout=None):
            if req.get_method() == "HEAD":
                raise urllib.error.HTTPError(req.full_url, 405, "Method Not Allowed", {}, None)
            raise urllib.error.HTTPError(req.full_url, 500, "Server Error", {}, None)

        with patch("urllib.request.urlopen", side_effect=side_effect) as opened:
            self.assertFalse(_url_reachable("https://example.com/head-disallowed"))
        self.assertEqual(opened.call_count, 2)


if __name__ == "__main__":
    unittest.main()
