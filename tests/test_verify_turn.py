"""ターン終了時の検証フック（Stop hook 向け）の挙動を、kb CLI のスタブで確認する。"""

import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "verify_turn.sh"


class VerifyTurnTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.bin = self.root / "stub-bin"
        self.bin.mkdir()
        self.calls = self.root / "kb-calls.txt"
        (self.root / "kb-domain.yml").write_text("domain:\n  content_root: knowledge\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _stub_kb(self, failing_subcommand: str | None = None) -> None:
        fail = failing_subcommand or "__none__"
        kb = self.bin / "kb"
        kb.write_text(
            "#!/bin/bash\n"
            f'echo "$*" >> {self.calls}\n'
            f'if [ "$*" = "{fail}" ]; then echo "検証エラーの詳細" >&2; exit 1; fi\n'
            "exit 0\n",
            encoding="utf-8",
        )
        kb.chmod(kb.stat().st_mode | stat.S_IXUSR)

    def _run(self, payload: dict | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", str(SCRIPT)], cwd=self.root, capture_output=True, text=True,
            input=json.dumps(payload or {}),
            env={**os.environ, "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}"},
        )

    def test_succeeds_quietly_when_checks_pass(self):
        self._stub_kb()
        result = self._run()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual("validate\nsync --check\n", self.calls.read_text(encoding="utf-8"))

    def test_blocks_the_turn_with_exit_code_two_when_validate_fails(self):
        self._stub_kb(failing_subcommand="validate")
        result = self._run()
        # exit 2 でなければ stderr が Claude に返らず、そのままターンが終わってしまう
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("検証エラーの詳細", result.stderr)

    def test_blocks_the_turn_when_generated_files_are_stale(self):
        self._stub_kb(failing_subcommand="sync --check")
        result = self._run()
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("kb sync", result.stderr)

    def test_does_not_run_again_when_already_invoked_from_a_stop_hook(self):
        """stop_hook_active のときに走ると、ブロックと再開が延々と繰り返される。"""
        self._stub_kb(failing_subcommand="validate")
        result = self._run({"stop_hook_active": True})
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertFalse(self.calls.exists())

    def test_skips_when_the_directory_is_not_a_kb(self):
        """KB 以外の作業ディレクトリで Claude を使うときに邪魔をしない。"""
        self._stub_kb()
        (self.root / "kb-domain.yml").unlink()
        result = self._run()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertFalse(self.calls.exists())


if __name__ == "__main__":
    unittest.main()
