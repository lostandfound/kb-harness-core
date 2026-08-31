import sys
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from rag_smoke import evaluate, rank_documents


class RagSmokeTest(unittest.TestCase):
    def setUp(self):
        self.documents = {
            "/products/aip.md": "Palantir AIP 生成AIを業務データと業務プロセスへ接続する。",
            "/products/foundry.md": "Palantir Foundry データ統合と業務アプリケーションの基盤。",
            "/concepts/ontology.md": "Ontology 業務オブジェクト、関係、アクションを表現する。",
        }

    def test_ranks_lexically_related_document_first(self):
        ranked = rank_documents("AIPは生成AIをどう業務へ接続するか", self.documents)

        self.assertEqual(ranked[0], "/products/aip.md")

    def test_evaluate_passes_when_expected_evidence_is_retrieved(self):
        entries = [
            {
                "id": "q001",
                "query": "Ontologyの業務オブジェクトとは何か",
                "evidence": ["/concepts/ontology.md"],
            }
        ]

        self.assertEqual(evaluate(entries, self.documents, limit=2), [])

    def test_evaluate_reports_query_with_unretrieved_evidence(self):
        entries = [
            {
                "id": "q002",
                "query": "zxqjvbnm",
                "evidence": ["/concepts/ontology.md"],
            }
        ]

        failures = evaluate(entries, self.documents, limit=1)
        self.assertEqual(failures[0]["id"], "q002")


if __name__ == "__main__":
    unittest.main()
