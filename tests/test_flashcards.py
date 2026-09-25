from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import HTTPServer
from pathlib import Path
from unittest.mock import patch

from kb_harness.cli import main
from kb_harness.flashcards import export_flashcards
from kb_harness.project import Project
from kb_harness.serve.server import make_handler


class FlashcardsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "content").mkdir()
        (self.root / "kb-domain.yml").write_text(
            "domain:\n  name: Test KB\n  kb_title: Test Knowledge Base\n  content_root: content\n"
            "index:\n  tag_labels:\n    topic-one: Topic One\n",
            encoding="utf-8",
        )
        (self.root / "content" / "vocabulary.yml").write_text(
            "types:\n  Concept:\n    directory: concepts\ntags:\n  - topic-one\n"
            "predicates:\n  related-to:\n    description: Related\n    domain: [Concept]\n    range: [Concept]\n",
            encoding="utf-8",
        )
        concepts = self.root / "content" / "concepts"
        concepts.mkdir()
        (concepts / "first.md").write_text(
            "---\ntype: Concept\ntitle: First\ndescription: First overview.\ntags: [topic-one]\n"
            "relations:\n  - predicate: related-to\n    target: /concepts/second.md\n---\n"
            "## Details\n\nThe full explanation links to [Second](/concepts/second.md).\n",
            encoding="utf-8",
        )
        (concepts / "second.md").write_text(
            "---\ntype: Concept\ntitle: Second\ndescription: Second overview.\ntags: [topic-one]\n---\n"
            "## More\n\nAdditional information.\n",
            encoding="utf-8",
        )
        self.project = Project.discover(self.root)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_exports_generic_items_details_and_bidirectional_relations(self) -> None:
        payload = export_flashcards(self.project)
        items = {item["id"]: item for item in payload["entities"]}
        first = items["/concepts/first.md"]
        second = items["/concepts/second.md"]
        self.assertEqual(payload["title"], "Test Knowledge Base")
        self.assertEqual(payload["tagLabels"], {"topic-one": "Topic One"})
        self.assertIn("The full explanation", first["details"])
        self.assertEqual(first["related"][0]["id"], second["id"])
        self.assertEqual(second["related"][0]["id"], first["id"])

    def test_exports_predicate_labels_from_vocabulary(self) -> None:
        payload = export_flashcards(self.project)
        self.assertEqual(payload["predicates"], {"related-to": "Related"})

    def test_script_has_no_domain_specific_predicates(self) -> None:
        script = (Path(__file__).resolve().parents[1] / "src" / "kb_harness" / "serve" / "static" / "flashcards.js")
        text = script.read_text(encoding="utf-8")
        for predicate in ("used-for", "production-involves"):
            self.assertNotIn(predicate, text)
        self.assertIn("data.predicates", text)
        self.assertNotIn('brandFirst: "学習"', text)

    def test_flashcards_view_and_api_work_without_graph_json(self) -> None:
        server = HTTPServer(("127.0.0.1", 0), make_handler(self.project, view="flashcards"))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            conn = HTTPConnection("127.0.0.1", server.server_address[1])
            conn.request("GET", "/")
            page = conn.getresponse()
            self.assertEqual(page.status, 200)
            self.assertIn("/flashcards.js", page.read().decode("utf-8"))
            conn.request("GET", "/api/flashcards")
            response = conn.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(len(json.loads(response.read())["entities"]), 2)
            conn.request("GET", "/flashcards.js")
            asset = conn.getresponse()
            self.assertEqual(asset.status, 200)
            conn.request("GET", "/flashcards/../../../../kb-domain.yml")
            self.assertEqual(conn.getresponse().status, 404)
            conn.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_flashcards_cli_selects_flashcards_view(self) -> None:
        with patch("kb_harness.cli.serve") as serve_spy:
            code = main(["flashcards", "--start", str(self.root), "--port", "8123", "--open"])
        self.assertEqual(code, 0)
        serve_spy.assert_called_once_with(
            self.project, port=8123, open_browser=True, view="flashcards"
        )


if __name__ == "__main__":
    unittest.main()
