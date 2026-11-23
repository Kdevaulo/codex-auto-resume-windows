"""Account switching's test for another engine on this Codex home asks core's rule for what an engine is (review-core C2).

`swap.other_engines` counted every process of a file called codex.exe, whatever its case, but the app main's
descendants. Core's rule since the fourth round's A3 (`pairing.engine_row`) is that a codex.exe where the app's main is -
the package's `app\\Codex.exe`, its 20 KB update trampoline, or a main an update renamed Codex.exe (review K7) - is never
an engine. So a renamed main, or the trampoline left running with the app closed, read as "another engine runs": every
automatic switch waited `engine_alive`, and a person's switch was refused, while it stood. Now the edition asks
`pairing.engine_row`, and the two agree.

Fixture rows only (test_pairing_roles' rows and its folder): no process is read, opened or ended.

    CODEX_AR_EDITION=advanced PYTHONPATH="src;advanced/src;advanced/tests;tests" python -m unittest test_advanced_swap_engine_row
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from codex_auto_resume.codex import pairing  # noqa: E402
from codex_auto_resume.domain.ids import CODEX_APP_FAMILY  # noqa: E402
from codex_auto_resume_advanced.codex import swap  # noqa: E402
import test_pairing_roles as roles  # noqa: E402  (a module, so its cases are not bound here)

row, ENGINE = roles.row, roles.ENGINE
SLOT = roles.FOLDER + r"\app\Codex.exe"


class EngineRowTests(roles.Case):
    def other(self, rows, app_open):
        with patch.object(pairing, "_OWN", set()):
            return swap.other_engines(rows, app_open=app_open)

    def test_a_main_renamed_codex_exe_is_not_another_engine(self):
        """Fails with the file name: the renamed main itself counts, and every switch waits while the app is open."""
        main = row(10, 1, SLOT, 100, CODEX_APP_FAMILY)
        server = row(20, 10, ENGINE, 200)
        self.assertFalse(pairing.engine_row(main))
        self.assertFalse(self.other([main, server], app_open=True))

    def test_the_trampoline_left_running_is_not_another_engine(self):
        """Fails with the file name: the trampoline alone, the app closed, read as an engine on this home."""
        trampoline = row(30, 1, SLOT, 300, CODEX_APP_FAMILY)
        self.assertFalse(self.other([trampoline], app_open=False))

    def test_a_real_engine_still_counts(self):
        self.assertTrue(self.other([row(40, 1, ENGINE, 400)], app_open=False))
        self.assertTrue(self.other([row(41, 1, roles.FOLDER + r"\app\resources\codex.exe", 410)], app_open=False),
                        "the package's own engine, below the main's folder, is one (#58)")

    def test_core_and_the_edition_agree(self):
        main = row(10, 1, SLOT, 100, CODEX_APP_FAMILY)
        rows = [main, row(20, 10, ENGINE, 200)]
        self.assertEqual([each["pid"] for each in rows if pairing.engine_row(each)], [20])
        self.assertFalse(self.other(rows, app_open=True))


if __name__ == "__main__":
    unittest.main()
