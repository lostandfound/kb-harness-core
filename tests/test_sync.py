import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kb_harness.sync import apply_changes_atomically


class SyncTest(unittest.TestCase):
    def test_rolls_back_previous_replacement_when_later_replacement_fails(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            first = root / "first.txt"
            second = root / "second.txt"
            first.write_text("first original", encoding="utf-8")
            second.write_text("second original", encoding="utf-8")
            calls = 0

            def replace(source: Path, target: Path):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("simulated replacement failure")
                os.replace(source, target)
                return target

            with patch("kb_harness.sync.Path.replace", autospec=True, side_effect=replace):
                with self.assertRaisesRegex(OSError, "simulated"):
                    apply_changes_atomically(
                        {first: "first changed", second: "second changed"}
                    )

            self.assertEqual(first.read_text(encoding="utf-8"), "first original")
            self.assertEqual(second.read_text(encoding="utf-8"), "second original")


if __name__ == "__main__":
    unittest.main()
