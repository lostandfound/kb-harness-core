"""改版で既存出典の記述が失われていないかを検出する仕組みの振る舞いを確認する。"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_source_attrition.py"

sys.path.insert(0, str(REPO_ROOT / "scripts"))

from check_source_attrition import detect_attrition  # noqa: E402


def _entity(sources: list[str], body: str) -> str:
    listed = "\n".join(f"- 'ref: {ref}'" for ref in sources)
    return f"---\ntype: Concept\ntitle: t\nsources:\n{listed}\n---\n\n{body}\n"


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=True,
        env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
             "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"},
    )


class DetectAttritionTest(unittest.TestCase):
    def test_reports_ref_whose_attributions_all_disappeared(self):
        before = _entity(["a", "b"], "段落1（出典: a）\n\n段落2（出典: b）")
        after = _entity(["a", "b"], "段落2を書き直した（出典: b）")
        self.assertEqual([("a", 1, 0)], detect_attrition(before, after))

    def test_ignores_partial_decrease_by_default(self):
        before = _entity(["a"], "段落1（出典: a）\n\n段落2（出典: a）")
        after = _entity(["a"], "段落をまとめた（出典: a）")
        self.assertEqual([], detect_attrition(before, after))

    def test_reports_when_most_of_the_attributions_disappeared(self):
        """改版で本文を書き直し、先行出典の記述がわずかに残るだけになった場合を捕まえる。"""
        before = _entity(["a", "b"], "\n\n".join(f"段落{i}（出典: a）" for i in range(6)))
        after = _entity(["a", "b"], "別の出典で書き直した（出典: b）\n\n名残（出典: a）")
        self.assertEqual([("a", 6, 1)], detect_attrition(before, after))

    def test_reports_partial_decrease_in_strict_mode(self):
        before = _entity(["a"], "段落1（出典: a）\n\n段落2（出典: a）")
        after = _entity(["a"], "段落をまとめた（出典: a）")
        self.assertEqual([("a", 2, 1)], detect_attrition(before, after, strict=True))

    def test_reports_ref_dropped_from_front_matter(self):
        before = _entity(["a", "b"], "段落1（出典: a）\n\n段落2（出典: b）")
        after = _entity(["b"], "段落1（出典: a）\n\n段落2（出典: b）")
        self.assertEqual([("a", 1, 0)], detect_attrition(before, after))

    def test_counts_each_ref_in_a_comma_separated_attribution(self):
        before = _entity(["a", "b"], "両方が述べる（出典: a,b）")
        after = _entity(["a", "b"], "片方だけにした（出典: b）")
        self.assertEqual([("a", 1, 0)], detect_attrition(before, after))

    def test_allows_additions(self):
        before = _entity(["a"], "段落1（出典: a）")
        after = _entity(["a", "b"], "段落1（出典: a）\n\n追記（出典: b）")
        self.assertEqual([], detect_attrition(before, after))

    def test_ignores_files_without_front_matter_sources(self):
        before = "# 覚書\n\n本文（出典: a）\n"
        after = "# 覚書\n\n本文\n"
        self.assertEqual([], detect_attrition(before, after))


class CheckSourceAttritionCliTest(unittest.TestCase):
    """ステージ済みの変更を既定の対象にすることを、一時リポジトリで確認する。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _git(self.root, "init", "-q")
        self.target = self.root / "knowledge" / "concepts" / "x.md"
        self.target.parent.mkdir(parents=True)
        self.target.write_text(
            _entity(["a", "b"], "段落1（出典: a）\n\n段落2（出典: b）"), encoding="utf-8"
        )
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "-m", "init")

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, *args: str, env_extra: dict | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args], cwd=self.root,
            capture_output=True, text=True, env={**os.environ, **(env_extra or {})},
        )

    def test_fails_when_staged_change_drops_an_existing_source(self):
        self.target.write_text(_entity(["a", "b"], "段落2だけ（出典: b）"), encoding="utf-8")
        _git(self.root, "add", "-A")
        result = self._run()
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("a", result.stderr)
        self.assertIn("knowledge/concepts/x.md", result.stderr)

    def test_passes_when_nothing_is_lost(self):
        self.target.write_text(
            _entity(["a", "b"], "段落1（出典: a）\n\n段落2を直した（出典: b）"), encoding="utf-8"
        )
        _git(self.root, "add", "-A")
        result = self._run()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_passes_for_newly_added_files(self):
        new = self.root / "knowledge" / "concepts" / "y.md"
        new.write_text(_entity(["a"], "新規（出典: a）"), encoding="utf-8")
        _git(self.root, "add", "-A")
        result = self._run()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_can_be_overridden_by_environment_variable(self):
        self.target.write_text(_entity(["a", "b"], "段落2だけ（出典: b）"), encoding="utf-8")
        _git(self.root, "add", "-A")
        result = self._run(env_extra={"KB_ALLOW_SOURCE_ATTRITION": "1"})
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
