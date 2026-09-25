"""--check-urls が DOI を出版社へ辿らず、DOI レジストリで登録を確かめる。"""

import io
import json
import unittest
from unittest.mock import patch

from kb_harness.validation import _doi_from_url, _doi_registered


def _response(record):
    body = io.BytesIO(json.dumps(record).encode("utf-8"))
    body.__enter__ = lambda self=body: self
    body.__exit__ = lambda *args: None
    return body


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
            self.assertFalse(_doi_registered("10.1000/abc"))

    def test_レジストリに届かなければ未登録として扱う(self):
        with patch("urllib.request.urlopen", side_effect=OSError("offline")):
            self.assertFalse(_doi_registered("10.1000/abc"))


if __name__ == "__main__":
    unittest.main()
