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
  Person:
    directory: people
  Claim:
    directory: claims
    graph: false
predicates:
  taught:
    description: teacher to student
    domain: [Person]
    range: [Person]
tags: [history]
"""

PERSON = """\
---
type: Person
title: {title}
description: Test person.
tags: [history]
timestamp: 2026-09-01T00:00:00Z
sources: [Test source]
---
Body.
"""

CLAIM = """\
---
type: Claim
title: Teacher taught student
description: Disputed teaching relation.
tags: [history]
timestamp: 2026-09-01T00:00:00Z
subject: /people/teacher.md
predicate: taught
object: /people/student.md
status: disputed
confidence: C
sources: [Test source]
---
Body.
"""


class ClaimTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        (self.root / "people").mkdir()
        (self.root / "claims").mkdir()
        (self.root / "vocabulary.yml").write_text(VOCAB, encoding="utf-8")
        (self.root / "people" / "teacher.md").write_text(
            PERSON.format(title="Teacher"), encoding="utf-8"
        )
        (self.root / "people" / "student.md").write_text(
            PERSON.format(title="Student"), encoding="utf-8"
        )
        self.claim_path = self.root / "claims" / "teacher-taught-student.md"
        self.claim_path.write_text(CLAIM, encoding="utf-8")

    def tearDown(self):
        self.tempdir.cleanup()

    def test_valid_claim_passes_validation(self):
        self.assertEqual(validate(self.root), [])

    def test_invalid_claim_is_rejected(self):
        self.claim_path.write_text(
            CLAIM.replace("status: disputed", "status: unknown"), encoding="utf-8"
        )
        self.assertTrue(any("status" in error for error in validate(self.root)))

    def test_claim_is_exported_separately(self):
        graph = export_graph(self.root)
        self.assertEqual(len(graph["nodes"]), 2)
        self.assertEqual(graph["edges"], [])
        self.assertEqual(graph["claims"], [{
            "path": "/claims/teacher-taught-student.md",
            "subject": "/people/teacher.md",
            "predicate": "taught",
            "object": "/people/student.md",
            "status": "disputed",
            "confidence": "C",
            "sources": ["Test source"],
        }])


if __name__ == "__main__":
    unittest.main()
