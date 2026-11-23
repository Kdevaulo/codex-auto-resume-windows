"""A terminal's engine is never the app's because the app was given its dead shell's id (v0.6.26, review K9).

audit-core C1 found core's parent walk taking a TUI for the app's server: the shell that started the TUI ended, Windows
gave its id to a helper the app started later, and the walk went from the TUI through that helper to the app main by ids
alone. Core's walk now holds every step to "a parent created after its child is not its parent"
(codex/pairing.under_app); the advanced edition's own walk - account switching's test for another engine on this
Codex home (codex/swap.other_engines) - got the same rule here. Rows with no creation time are walked as before.

Fixture rows only: no process is read, opened or ended.

    CODEX_AR_EDITION=advanced PYTHONPATH="src;advanced/src;advanced/tests;tests" python -m unittest test_advanced_swap_reused_parent
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from codex_auto_resume.codex import pairing  # noqa: E402
from codex_auto_resume_advanced.codex import swap  # noqa: E402

APP = "c:\\program files\\windowsapps\\openai.chatgpt_1.0.0.0_x64__abcdefghijklm\\app\\chatgpt.exe"
ENGINE = "c:\\fakelocalappdata\\openai\\codex\\bin\\abcdef0123456789\\codex.exe"
# audit-core C1's rows: the main, a helper given the id of the TUI's shell long after that shell ended, and the TUI.
MAIN = {"pid": 10, "parent": 1, "path": APP, "created": 100}
HELPER = {"pid": 999, "parent": 10, "path": APP, "created": 900}
TUI = {"pid": 40, "parent": 999, "path": ENGINE, "created": 400}


class ReusedParentTests(unittest.TestCase):
    def other(self, rows):
        with patch.object(pairing, "_app_main", lambda found: MAIN), patch.object(pairing, "_OWN", set()):
            return swap.other_engines(rows, app_open=True)

    def test_a_tui_under_a_helper_younger_than_it_is_another_engine(self):
        """Fails with the walk by ids alone: the TUI is taken for the app's own, and the account is swapped beside it."""
        self.assertTrue(self.other([MAIN, HELPER, TUI]))

    def test_the_apps_own_server_under_its_helper_is_the_apps(self):
        server = {"pid": 41, "parent": 999, "path": ENGINE, "created": 950}
        self.assertFalse(self.other([MAIN, HELPER, server]))

    def test_a_server_older_than_the_main_is_not_the_apps(self):
        server = {"pid": 42, "parent": 10, "path": ENGINE, "created": 50}
        self.assertTrue(self.other([MAIN, server]))

    def test_a_time_that_could_not_be_read_is_not_the_apps(self):
        server = {"pid": 43, "parent": 999, "path": ENGINE, "created": None}
        self.assertTrue(self.other([MAIN, HELPER, server]))

    def test_rows_with_no_times_are_walked_by_ids_as_before(self):
        main = {"pid": 10, "parent": 1, "path": APP}
        server = {"pid": 11, "parent": 10, "path": ENGINE}
        exec_server = {"pid": 12, "parent": 11, "path": ENGINE}
        with patch.object(pairing, "_app_main", lambda found: main), patch.object(pairing, "_OWN", set()):
            self.assertFalse(swap.other_engines([main, server, exec_server], app_open=True))

    def test_core_and_the_edition_agree_on_c1s_rows(self):
        self.assertFalse(pairing.under_app([MAIN, HELPER, TUI], TUI, MAIN["pid"]))
        self.assertTrue(self.other([MAIN, HELPER, TUI]))


if __name__ == "__main__":
    unittest.main()
