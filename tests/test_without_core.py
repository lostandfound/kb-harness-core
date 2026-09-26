"""kb-ontology-core が無い環境でのハーネスの挙動。

サブプロセスで sys.modules["kb_ontology_core"] = None を置き、pip 導入と
兄弟ディレクトリのどちらのフォールバックも効かない状態を作る。
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"

INDEX = (
    "---\ntype: Index\ntitle: {title}\ndescription: 一覧である。\ntags: [index]\n"
    "timestamp: 2026-09-01T00:00:00Z\n---\n\n## エンティティ一覧\n\n{links}"
)
ENTITY = (
    "---\ntype: Concept\ntitle: 概念\ndescription: 概念である。\ntags: [index]\n"
    "timestamp: 2026-09-01T00:00:00Z\nsources: ['https://example.org/']\n---\n\n## 概要\n\n本文である。\n"
)
CLAIM = (
    "---\ntype: Claim\ntitle: 主張\ndescription: 主張である。\ntags: [index]\n"
    "timestamp: 2026-09-01T00:00:00Z\nsources: ['https://example.org/']\n"
    "subject: /concepts/a.md\npredicate: related-to\nobject: /concepts/b.md\nstatus: proposed\nconfidence: C\n"
    "---\n\n## 概要\n\n本文である。\n"
)


def build_kb(root: Path, *, with_claim: bool) -> None:
    content = root / "knowledge"
    (root / "kb-domain.yml").write_text("domain:\n  content_root: knowledge\n", encoding="utf-8")
    vocab = "types:\n  Concept:\n    directory: concepts\n"
    if with_claim:
        vocab += "  Claim:\n    directory: claims\n    extra_fields: [subject, status, confidence]\n"
    vocab += "predicates:\n  related-to:\n    description: 関連\ntags: [index]\n"
    (content / "concepts").mkdir(parents=True)
    (content / "vocabulary.yml").write_text(vocab, encoding="utf-8")
    (content / "references.yml").write_text("{}\n", encoding="utf-8")
    for slug in ("a", "b"):
        (content / "concepts" / f"{slug}.md").write_text(ENTITY, encoding="utf-8")
    (content / "concepts" / "index.md").write_text(
        INDEX.format(title="concepts", links="- [a](/concepts/a.md)\n- [b](/concepts/b.md)\n"), encoding="utf-8"
    )
    links = "- [concepts](/concepts/index.md)\n"
    if with_claim:
        (content / "claims").mkdir()
        (content / "claims" / "c.md").write_text(CLAIM, encoding="utf-8")
        (content / "claims" / "index.md").write_text(INDEX.format(title="claims", links="- [c](/claims/c.md)\n"), encoding="utf-8")
        links += "- [claims](/claims/index.md)\n"
    (content / "index.md").write_text(INDEX.format(title="root", links=links), encoding="utf-8")


def run_kb_without_core(root: Path, *args: str) -> tuple[int, dict]:
    code = (
        "import sys, json\n"
        "sys.modules['kb_ontology_core'] = None\n"
        f"sys.path.insert(0, {str(SRC)!r})\n"
        "from kb_harness.cli import main\n"
        f"raise SystemExit(main({list(args)!r} + ['--start', {str(root)!r}, '--format', 'json']))\n"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    payload = proc.stdout.strip() or proc.stderr.strip()
    return proc.returncode, json.loads(payload)


class WithoutCoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_validate_and_doctor_work_for_a_kb_without_claims(self):
        build_kb(self.root, with_claim=False)
        code, result = run_kb_without_core(self.root, "validate")
        self.assertEqual((code, result["ok"]), (0, True), result)
        code, result = run_kb_without_core(self.root, "sync")
        self.assertEqual(code, 0, result)
        code, result = run_kb_without_core(self.root, "sync", "--check")
        self.assertEqual(code, 0, result)
        code, result = run_kb_without_core(self.root, "doctor")
        self.assertEqual(code, 0, result)
        codes = {d["code"]: d for d in result["diagnostics"]}
        self.assertIn("doctor.ontology.not_installed", codes)
        self.assertEqual(codes["doctor.ontology.not_installed"].get("severity"), "warning")

    def test_claims_fail_with_a_stable_diagnostic(self):
        build_kb(self.root, with_claim=True)
        code, result = run_kb_without_core(self.root, "validate")
        self.assertEqual(code, 1, result)
        self.assertEqual([d["code"] for d in result["diagnostics"]], ["ontology.core.missing"])
        code, result = run_kb_without_core(self.root, "graph", "build", "--dry-run")
        self.assertEqual(code, 1, result)
        self.assertEqual([d["code"] for d in result["diagnostics"]], ["ontology.core.missing"])


if __name__ == "__main__":
    unittest.main()
