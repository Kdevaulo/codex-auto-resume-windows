"""v0.6.26 (review of the third round, K7): an app main renamed Codex.exe is still the app's main.

Update resilience #5 made a main or a helper an update renamed still the app's - by its package's folder and family -
but refused any file called codex.exe, inside the package too, so the likeliest rename of a package called OpenAI.Codex
was never the main: the app read as open with no server matched, for ever. Now a codex.exe where the main is, directly
in the package's `app` folder, is the app's like any other name; one in a folder below it - where the package keeps its
own engine (#58), which a terminal may run - is still an engine and never one of the app's own processes.

Synthetic rows only: no process is asked, and the Restart Manager is a stub (test_pairing_roles' Case).
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

_HERE = str(Path(__file__).resolve().parent)
for entry in (str(Path(_HERE).parent / "src"), _HERE):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from codex_auto_resume.codex import layout, pairing  # noqa: E402
from codex_auto_resume.domain.ids import CODEX_APP_FAMILY  # noqa: E402
import test_pairing_roles as roles  # noqa: E402  (a module, so its cases are not bound here)

MAIN = roles.row(10, 1, roles.FOLDER + r"\app\Codex.exe", 100, CODEX_APP_FAMILY)
SERVER = roles.row(20, 10, roles.ENGINE, 200)


class MainNamedCodexTests(roles.Case):
    def test_a_main_renamed_codex_exe_is_the_main_and_its_server_is_paired(self):
        rows = [MAIN, SERVER]
        self.assertTrue(pairing.app_process(MAIN))
        self.assertEqual(pairing._app_main(rows)["pid"], 10)
        self.assertTrue(pairing.app_running(rows))
        self.assertEqual(self.pair(rows, []), 20)
        self.assertEqual(layout.snapshot(rows)["shape"], "single_child")

    def test_any_case_of_the_name_where_the_main_is(self):
        for name in ("codex.exe", "CODEX.EXE"):
            with self.subTest(name=name):
                main = dict(MAIN, path=roles.FOLDER + "\\app\\" + name)
                self.assertEqual(self.pair([main, SERVER], []), 20)

    def test_the_packages_own_engine_below_it_is_still_no_app_process(self):
        engine = roles.FOLDER + r"\app\resources\codex.exe"
        tui = roles.row(31, 30, engine, 310, CODEX_APP_FAMILY)
        self.assertFalse(pairing.app_process(tui))
        shell = roles.row(30, 1, roles.SHELL, 300)
        rows = [roles.MAIN, shell, tui]
        self.assertFalse(pairing.under_app(rows, tui, 10))
        self.assertEqual(len(pairing.app_mains(rows)), 1, "the engine a terminal runs is no second main")

    def test_without_the_family_or_outside_the_package_it_is_not_the_apps(self):
        self.assertFalse(pairing.app_process(dict(MAIN, family=None)))
        self.assertFalse(pairing.app_process(dict(MAIN, path=r"C:\Somewhere\app\Codex.exe")))


if __name__ == "__main__":
    unittest.main()
