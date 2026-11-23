"""v0.6.26 (fourth round, audit-core A1): a package program outside the main's place is never the app's main.

Update resilience #5 made any file of the Codex package's folder that carries the package family one of the app's
processes, and `app_mains` counted every such process whose parent is not of the package. The package also ships
tools in folders below `app` - the Chrome native host (an app execution alias Chrome starts), the command runner, rg,
node, the code-mode host - so one of them started from outside the app became a "main". Measured on the owner's PC on
2026-11-23 with the app closed: the inventory's one row was the Chrome native host, parent cmd.exe, of the package's
family; the app read as running, and with the app open it would read as two mains and every recovery would wait.

Now only a process where the main can be (`_main_place`: directly in the package's `app` folder or in the package's
own folder) is a main; another package program is the app's only under a main. Synthetic rows only: no process is
asked, and the Restart Manager is a stub (test_pairing_roles' Case).
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

row, FOLDER, ENGINE = roles.row, roles.FOLDER, roles.ENGINE
# The row measured on 2026-11-23: the package's Chrome native host, its parent cmd.exe - not a program the inventory
# lists, so its pid is in no row.
HOST = row(50, 7, FOLDER + r"\app\plugins\chrome\extension-host\windows\x64\extension-host.exe", 500, CODEX_APP_FAMILY)
UTILITY = row(11, 10, roles.PACKAGE, 110, CODEX_APP_FAMILY)
SERVER = row(20, 11, ENGINE, 200)
EXEC = row(21, 10, ENGINE, 210)
OPEN = [roles.MAIN, UTILITY, SERVER, EXEC]                  # 26.1117 (#67): the server under the utility process
TOOLS = {
    "rg.exe under the server": row(60, 20, FOLDER + r"\app\resources\rg.exe", 600, CODEX_APP_FAMILY),
    "node.exe under the server": row(61, 20, FOLDER + r"\app\cua_node\bin\node.exe", 610, CODEX_APP_FAMILY),
    "the code-mode host under the server": row(62, 20, FOLDER + r"\app\resources\codex-code-mode-host.exe", 620,
                                               CODEX_APP_FAMILY),
    "the command runner from a shell": row(63, 30, FOLDER + r"\app\resources\codex-command-runner.exe", 630,
                                           CODEX_APP_FAMILY),
    "the Chrome native host from cmd.exe": HOST,
}


class PackageToolTests(roles.Case):
    def test_the_measured_row_alone_is_no_main_and_the_app_is_closed(self):
        """Fails with the fix reverted: app_mains returned [the host], and app_running said True."""
        rows = [HOST]
        self.assertTrue(pairing.app_process(HOST), "it is a process of the package")
        self.assertEqual(pairing.app_mains(rows), [])
        self.assertFalse(pairing.app_running(rows))
        found = layout.snapshot(rows)
        self.assertEqual((found["mains"], found["helpers"], found["shape"]), (0, 0, "closed"))

    def test_beside_the_apps_real_main_there_is_one_main_and_the_server_pairs(self):
        """Fails with the fix reverted: two mains, desktop_main_missing_or_ambiguous, and the shape none."""
        for name, tool in TOOLS.items():
            with self.subTest(tool=name):
                rows = OPEN + [tool]
                self.assertEqual([main["pid"] for main in pairing.app_mains(rows)], [10])
                self.assertTrue(pairing.app_running(rows))
                self.assertEqual(self.pair(rows, [self.held(SERVER)]), 20)
                self.assertEqual(pairing.server_engines(rows), frozenset({ENGINE}))
                self.assertFalse(pairing.session_kind(rows, self.held(SERVER), ENGINE))
                found = layout.snapshot(rows, ENGINE, {"server_holds": True})
                self.assertEqual((found["mains"], found["helpers"], found["shape"]), (1, 1, "helper_parented"))

    def test_a_package_tool_the_main_starts_is_a_helper(self):
        tool = row(64, 10, FOLDER + r"\app\native\dictation-ducking.exe", 640, CODEX_APP_FAMILY)
        rows = OPEN + [tool]
        self.assertTrue(pairing.under_app(rows, tool, 10))
        self.assertEqual(layout.snapshot(rows)["helpers"], 2)
        self.assertEqual(self.pair(rows, [self.held(SERVER)]), 20)

    def test_a_renamed_main_where_the_main_can_be_is_still_the_main(self):
        """Update resilience #5 and review K7 hold: in the `app` folder, in the package's own folder, named Codex.exe."""
        for path in (FOLDER + r"\app\OpenAI Codex.exe", FOLDER + r"\OpenAI Codex.exe", FOLDER + r"\app\Codex.exe"):
            with self.subTest(path=path):
                rows = [row(10, 1, path, 100, CODEX_APP_FAMILY), row(20, 10, ENGINE, 200), HOST]
                self.assertEqual([main["pid"] for main in pairing.app_mains(rows)], [10])
                self.assertTrue(pairing.app_running(rows))
                self.assertEqual(self.pair(rows, []), 20)


if __name__ == "__main__":
    unittest.main()
