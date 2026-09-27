"""--check-urls が DOI を出版社へ辿らず、DOI レジストリで登録を確かめる。"""

import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from contextlib import redirect_stdout

from kb_harness.cli import main
from kb_harness.validation import _doi_from_url, _doi_registered, check_urls


def _response(record):
    body = io.BytesIO(json.dumps(record).encode("utf-8"))
    body.__enter__ = lambda self=body: self
    body.__exit__ = lambda *args: None
    return body


def _http_error(code):
    return urllib.error.HTTPError("https://doi.org/api/handles/x", code, "error", {}, io.BytesIO(b"{}"))


class DoiFromUrlTest(unittest.TestCase):
    def test_doi_orgのURLからDOIを取り出す(self):
        self.assertEqual(_doi_from_url("https://doi.org/10.1000/xyz%2F1"), "10.1000/xyz/1")
        self.assertEqual(_doi_from_url("https://dx.doi.org/10.1000/abc"), "10.1000/abc")

    def test_doi_org以外のURLはDOIとみなさない(self):
        self.assertIsNone(_doi_from_url("https://example.com/10.1000/abc"))
        self.assertIsNone(_doi_from_url("https://doi.org/"))


class DoiRegisteredTest(unittest.TestCase):
    def test_レジストリが同じハンドルを返せば登録済み(self):
        with patch("urllib.request.urlopen", return_value=_response({"responseCode": 1, "handle": "10.1000/ABC"})) as opened:
            self.assertTrue(_doi_registered("10.1000/abc"))
        self.assertIn("doi.org/api/handles/10.1000/abc", opened.call_args.args[0].full_url)

    def test_未登録の応答コードは未登録(self):
        with patch("urllib.request.urlopen", return_value=_response({"responseCode": 100, "handle": "10.1000/abc"})):
            self.assertIs(_doi_registered("10.1000/abc"), False)

    def test_レジストリの404は未登録(self):
        with patch("urllib.request.urlopen", side_effect=_http_error(404)):
            self.assertIs(_doi_registered("10.1000/abc"), False)

    def test_レジストリに届かなければ判定不能(self):
        with patch("urllib.request.urlopen", side_effect=OSError("offline")):
            self.assertIsNone(_doi_registered("10.1000/abc"))

    def test_レジストリの5xxは判定不能(self):
        with patch("urllib.request.urlopen", side_effect=_http_error(503)):
            self.assertIsNone(_doi_registered("10.1000/abc"))


class CheckUrlsDoiTest(unittest.TestCase):
    def _kb(self, tempdir):
        content = Path(tempdir) / "knowledge"
        content.mkdir()
        (content / "references.yml").write_text(
            "paper-a:\n  type: paper\n  author: A\n  title: A\n  doi: 10.1000/a\n"
            "paper-b:\n  type: paper\n  author: B\n  title: B\n  url: https://doi.org/10.1000/b\n",
            encoding="utf-8",
        )
        return content

    def test_未登録のDOIはERROR(self):
        with tempfile.TemporaryDirectory() as tempdir:
            content = self._kb(tempdir)
            warnings: list[str] = []
            with patch("kb_harness.validation._doi_registered", return_value=False):
                errors = check_urls(content, warnings=warnings)
        self.assertEqual(
            errors,
            [
                "ERROR /references.yml: DOI unregistered 10.1000/a (paper-a)",
                "ERROR /references.yml: DOI unregistered 10.1000/b (paper-b)",
            ],
        )
        self.assertEqual(warnings, [])

    def test_レジストリに届かないDOIはWARNINGでERRORにしない(self):
        with tempfile.TemporaryDirectory() as tempdir:
            content = self._kb(tempdir)
            warnings: list[str] = []
            with patch("kb_harness.validation._doi_registered", return_value=None):
                errors = check_urls(content, warnings=warnings)
        self.assertEqual(errors, [])
        self.assertEqual([w.code for w in warnings], ["validation.url.doi_registry_unreachable"] * 2)
        self.assertIn("10.1000/a (paper-a)", warnings[0])

    def test_DOIは出版社のURLへHTTPで辿らない(self):
        with tempfile.TemporaryDirectory() as tempdir:
            content = self._kb(tempdir)
            with patch("kb_harness.validation._doi_registered", return_value=True), patch(
                "kb_harness.validation._url_reachable"
            ) as reachable:
                self.assertEqual(check_urls(content), [])
        reachable.assert_not_called()


class ValidateCheckUrlsDoiCliTest(unittest.TestCase):
    def test_レジストリに届かないDOIはwarningsに入り終了コード0(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            content = root / "knowledge"
            (content / "notes").mkdir(parents=True)
            (root / "kb-domain.yml").write_text("domain:\n  content_root: knowledge\n", encoding="utf-8")
            (content / "vocabulary.yml").write_text(
                "types:\n  Note:\n    directory: notes\n    graph: false\npredicates: {}\ntags: []\n",
                encoding="utf-8",
            )
            (content / "notes" / "note.md").write_text(
                "---\ntype: Note\ntitle: note\ndescription: Description.\ntags: []\n"
                "timestamp: 2026-01-01T00:00:00Z\n"
                "sources:\n  - https://doi.org/10.1000/xyz\n---\n\nBody\n",
                encoding="utf-8",
            )
            output = io.StringIO()
            with patch("kb_harness.validation._doi_registered", return_value=None):
                with redirect_stdout(output):
                    exit_code = main(["validate", "--check-urls", "--start", str(root), "--format", "json"])
            result = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(result["diagnostics"], [])
        self.assertIn(
            "validation.url.doi_registry_unreachable",
            [warning["code"] for warning in result["warnings"]],
        )


if __name__ == "__main__":
    unittest.main()
