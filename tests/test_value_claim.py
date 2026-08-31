import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from export_graph import export_graph
from validate import validate

VOCAB = """\
types:
  Kata: {directory: kata}
  Claim: {directory: claims, graph: false}
predicates: {}
properties:
  established-year:
    domain: [Kata]
    value_type: year-expression
tags: [history]
"""

KATA = """\
---
type: Kata
title: Test kata
description: Test kata.
tags: [history]
timestamp: 2026-09-01T00:00:00Z
sources: [Test source]
---
Body.
"""

CLAIM = """\
---
type: Claim
title: Test kata year
description: Disputed year.
tags: [history]
timestamp: 2026-09-01T00:00:00Z
subject: /kata/test.md
property: established-year
value: "1950年代"
status: disputed
confidence: C
sources: [Test source]
---
Body.
"""

class ValueClaimTest(unittest.TestCase):
    def test_value_claim_validates_and_exports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "kata").mkdir()
            (root / "claims").mkdir()
            (root / "vocabulary.yml").write_text(VOCAB, encoding="utf-8")
            (root / "kata" / "test.md").write_text(KATA, encoding="utf-8")
            (root / "claims" / "test-year.md").write_text(CLAIM, encoding="utf-8")
            self.assertEqual(validate(root), [])
            claim = export_graph(root)["claims"][0]
            self.assertEqual(claim["property"], "established-year")
            self.assertEqual(claim["value"], "1950年代")
            self.assertNotIn("object", claim)

    def test_value_claim_rejects_partial_relation_form(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            (root / "kata").mkdir()
            (root / "claims").mkdir()
            (root / "vocabulary.yml").write_text(VOCAB, encoding="utf-8")
            (root / "kata" / "test.md").write_text(KATA, encoding="utf-8")
            mixed = CLAIM.replace(
                "property: established-year",
                "predicate: taught\nproperty: established-year",
            )
            (root / "claims" / "test-year.md").write_text(mixed, encoding="utf-8")

            self.assertTrue(any("Claim 形式" in error for error in validate(root)))


if __name__ == "__main__":
    unittest.main()
