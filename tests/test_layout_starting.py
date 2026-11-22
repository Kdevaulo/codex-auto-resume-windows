"""v0.6.26 (review of the third round, K8): an app that stays "starting" becomes a layout not tested on.

The layout catalogue counts the app open with no codex.exe under it ("starting": the app starting, or its server
restarting) as a tested shape. An app whose engine is no longer a codex.exe under it - renamed by an update, which the
inventory does not even list - reads "starting" for ever, so it was never said to run in a layout this version has not
been tested on, and no other rule said anything either. Now "starting" is a tested shape for STARTING_SECONDS of looks
running; past that it is not, until a look finds another shape.

Synthetic rows and a scratch folder only (test_pairing_roles' Case for the package folder).
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

_HERE = str(Path(__file__).resolve().parent)
for entry in (str(Path(_HERE).parent / "src"), _HERE):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from codex_auto_resume.codex import layout  # noqa: E402
from codex_auto_resume.domain.ids import CODEX_APP_FAMILY  # noqa: E402
import test_pairing_roles as roles  # noqa: E402  (a module, so its cases are not bound here)

HELPER = roles.row(11, 10, roles.PACKAGE, 110, CODEX_APP_FAMILY)
RENAMED = roles.row(20, 11, r"C:\FakeLocalAppData\OpenAI\Codex\bin\abcdef0123456789\codex-server.exe", 200)
SERVER = roles.row(21, 10, roles.ENGINE, 210)
TEN_MINUTES = 600.0          # layout.STARTING_SECONDS


class StartingTests(roles.Case):
    def setUp(self):
        super().setUp()
        self.now, self.lines = 0.0, []
        # The watch's clock is the process's monotonic one, read here.
        clock = patch("time.monotonic", side_effect=lambda: self.now)
        clock.start()
        self.addCleanup(clock.stop)
        self.watch = layout.Watch(self.home / "codex-layout.json", "0.6.26", self.lines.append)

    def look(self, rows, at):
        self.now = at
        return self.watch.look(layout.snapshot(rows), stamp=(1, 2), engine_version="0.170.0")

    def untested_lines(self):
        return [line for line in self.lines if "has not been tested on" in line]

    def test_an_engine_that_is_no_codex_exe_under_the_app_is_untested_after_ten_minutes(self):
        rows = [roles.MAIN, HELPER, RENAMED]
        self.assertEqual(layout.snapshot(rows)["shape"], "starting")
        self.assertTrue(self.look(rows, 0.0)["catalogued"])
        self.assertTrue(self.look(rows, TEN_MINUTES - 1)["catalogued"])
        self.assertEqual(self.untested_lines(), [])
        kept = self.look(rows, TEN_MINUTES)
        self.assertIs(kept["catalogued"], False)
        self.assertEqual(layout.read(self.home / "codex-layout.json")["catalogued"], False)
        self.assertEqual(len(self.untested_lines()), 1, "said once in the log when it turned")
        self.look(rows, TEN_MINUTES + 60)
        self.assertEqual(len(self.untested_lines()), 1)

    def test_a_server_that_comes_starts_it_again(self):
        starting = [roles.MAIN, HELPER]
        self.look(starting, 0.0)
        self.assertIs(self.look(starting, 700.0)["catalogued"], False)
        self.assertTrue(self.look([roles.MAIN, HELPER, SERVER], 710.0)["catalogued"])
        self.assertTrue(self.look(starting, 720.0)["catalogued"], "a restart of the server is starting again")
        self.assertTrue(self.look(starting, 720.0 + TEN_MINUTES - 1)["catalogued"])

    def test_ten_minutes_is_the_bound(self):
        self.assertEqual(getattr(layout, "STARTING_SECONDS", None), TEN_MINUTES)

    def test_the_app_closed_is_tested_however_long(self):
        self.look([], 0.0)
        self.assertTrue(self.look([], 10 * TEN_MINUTES)["catalogued"])


if __name__ == "__main__":
    unittest.main()
