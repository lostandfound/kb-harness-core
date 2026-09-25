"""互換スクリプトが、同じチェックアウトの src/kb_harness を使うことを確認する。"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
NAMES = ("export_graph.py", "generate_index.py", "new_entity.py", "validate.py")


class ScriptImportTest(unittest.TestCase):
    def test_古いkb_harnessが入っていてもチェックアウトのsrcを使う(self):
        with tempfile.TemporaryDirectory() as tempdir:
            # 何も持たない kb_harness を sys.path の先頭に置き、pip で入った古い版を模す
            stale = Path(tempdir) / "kb_harness"
            stale.mkdir()
            (stale / "__init__.py").write_text("STALE = True\n", encoding="utf-8")
            env = {**os.environ, "PYTHONPATH": tempdir}
            for name in NAMES:
                result = subprocess.run(
                    [sys.executable, str(SCRIPTS / name), "--help"],
                    capture_output=True, text=True, env=env, cwd=tempdir,
                )
                for marker in ("ImportError", "ModuleNotFoundError", "cannot import"):
                    self.assertNotIn(marker, result.stderr, name)
                # new_entity.py / validate.py は --help の前にスクリプトの位置から KB を探し、
                # ここでは見つからずに落ちる。import が通ったことだけを見る
                if name not in ("new_entity.py", "validate.py"):
                    self.assertEqual(result.returncode, 0, f"{name}: {result.stderr}")


if __name__ == "__main__":
    unittest.main()
