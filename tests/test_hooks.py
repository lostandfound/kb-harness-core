"""pre-commit テンプレートの挙動を、tests/ や evals/ を持たない導入先を模した一時リポジトリで確認する。"""

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK = REPO_ROOT / "scripts" / "hooks" / "pre-commit"
INSTALL = REPO_ROOT / "scripts" / "install-hooks.sh"


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=True,
        env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
             "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"},
    )


class PreCommitHookTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _git(self.root, "init", "-q")
        # 検証本体は導入先環境依存なので、呼ばれたサブコマンドを記録して成功する kb スタブに差し替える
        self.bin = self.root / "stub-bin"
        self.bin.mkdir()
        self.calls = self.root / "kb-calls.txt"
        kb = self.bin / "kb"
        kb.write_text(f"#!/bin/bash\necho \"$*\" >> {self.calls}\nexit 0\n", encoding="utf-8")
        kb.chmod(kb.stat().st_mode | stat.S_IXUSR)
        self.env = {**os.environ, "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}"}
        (self.root / "note.md").write_text("# note\n", encoding="utf-8")
        _git(self.root, "add", "note.md")

    def tearDown(self):
        self.tmp.cleanup()

    def _run_hook(self) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", str(HOOK)], cwd=self.root, capture_output=True, text=True, env=self.env
        )

    def test_passes_without_tests_or_evals_directories(self):
        result = self._run_hook()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("pytest", result.stdout + result.stderr)
        # 導入先の scripts/ に依存せず kb CLI だけを呼ぶ。evals が無いので eval smoke は呼ばれない
        self.assertEqual(self.calls.read_text(encoding="utf-8"), "validate\n")

    def test_runs_eval_smoke_only_when_eval_file_exists(self):
        (self.root / "evals").mkdir()
        (self.root / "evals" / "rag-eval.yml").write_text("queries: []\n", encoding="utf-8")
        result = self._run_hook()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.calls.read_text(encoding="utf-8"), "validate\neval smoke\n")

    def test_runs_pre_commit_d_scripts_in_order_and_stops_on_failure(self):
        hooks_dir = self.root / ".kb" / "hooks" / "pre-commit.d"
        hooks_dir.mkdir(parents=True)
        marker = self.root / "marker.txt"
        for name, body in (
            ("10-first.sh", f"echo first >> {marker}\n"),
            ("20-fail.sh", "echo failing >&2; exit 1\n"),
            ("30-never.sh", f"echo never >> {marker}\n"),
        ):
            script = hooks_dir / name
            script.write_text("#!/bin/bash\n" + body, encoding="utf-8")
            script.chmod(script.stat().st_mode | stat.S_IXUSR)

        result = self._run_hook()

        self.assertEqual(result.returncode, 1)
        self.assertEqual(marker.read_text(encoding="utf-8"), "first\n")
        self.assertIn("20-fail.sh", result.stderr)

    def test_install_hooks_copies_template_into_git_hooks(self):
        result = subprocess.run(
            ["bash", str(INSTALL)], cwd=self.root, capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        installed = self.root / ".git" / "hooks" / "pre-commit"
        self.assertEqual(installed.read_text(encoding="utf-8"), HOOK.read_text(encoding="utf-8"))
        self.assertTrue(installed.stat().st_mode & stat.S_IXUSR)


if __name__ == "__main__":
    unittest.main()
