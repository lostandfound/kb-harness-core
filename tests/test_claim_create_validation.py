import tempfile
import unittest
from pathlib import Path

import yaml

from kb_harness.claim import ClaimSpecError, plan_claim_create
from kb_harness.project import Project


class ClaimCreateValidationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        content = root / "knowledge"
        (content / "people").mkdir(parents=True)
        (content / "claims").mkdir()
        (content / "vocabulary.yml").write_text("types:\n  Person:\n    directory: people\n  Claim:\n    directory: claims\n    graph: false\npredicates:\n  taught:\n    domain: [Person]\n    range: [Person]\n", encoding="utf-8")
        (root / "kb-domain.yml").write_text("domain:\n  content_root: knowledge\n", encoding="utf-8")
        self.project = Project.from_config(root / "kb-domain.yml")
        for name in ("teacher", "student"):
            (content / "people" / f"{name}.md").write_text("---\ntype: Person\ntitle: Person\ndescription: Test\ntags: []\ntimestamp: 2026-01-01T00:00:00Z\nsources: [x]\n---\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def spec(self, **changes):
        data = {"subject": "/people/teacher.md", "predicate": "taught", "object": "/people/student.md", "status": "proposed", "confidence": "C", "sources": ["x"]}
        data.update(changes)
        path = Path(self.tmp.name) / "spec.yml"
        path.write_text(yaml.safe_dump(data), encoding="utf-8")
        return path

    def assert_rejected(self, **changes):
        before = sorted(self.project.content_root.rglob("*.md"))
        with self.assertRaises(ClaimSpecError):
            plan_claim_create(self.project, self.spec(**changes))
        self.assertEqual(before, sorted(self.project.content_root.rglob("*.md")))

    def test_missing_subject(self): self.assert_rejected(subject=None)
    def test_missing_object(self): self.assert_rejected(object=None)
    def test_unknown_predicate(self): self.assert_rejected(predicate="unknown")
    def test_domain_range_violation(self): self.assert_rejected(object="/people/missing.md")
    def test_relation_duplicate(self):
        (self.project.content_root / "people" / "teacher.md").write_text("---\ntype: Person\nrelations:\n - predicate: taught\n   target: /people/student.md\n---\n", encoding="utf-8")
        self.assert_rejected()
    def test_claim_duplicate(self):
        (self.project.content_root / "claims" / "existing.md").write_text("---\ntype: Claim\nsubject: /people/teacher.md\npredicate: taught\nobject: /people/student.md\nstatus: proposed\nconfidence: C\nsources: [x]\n---\n", encoding="utf-8")
        self.assert_rejected()

    def test_valid_claim_plans(self):
        plan = plan_claim_create(self.project, self.spec())
        self.assertGreaterEqual(len(plan.changes), 2)
