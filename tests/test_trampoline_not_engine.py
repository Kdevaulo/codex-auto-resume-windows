"""v0.6.26 (fourth round, audit-core A3): the Codex package's `app\\Codex.exe` is never taken for an engine.

The installed package's `app\\Codex.exe` is a 20 KB OpenAI-signed update trampoline (windows_update_trampoline), and the
place where a main an update renamed Codex.exe sits (review K7). Run under the main, it was counted among the engines
the app serves (`server_engines`), so discovery would have run it with `--version` and `queue --help` as a candidate
engine - against "nothing on the off chance". Now a codex.exe where the main is (`_main_slot`) is an app process and
never an engine (`engine_row`): not paired, not served, not counted by the layout, never handed to discovery.

Synthetic rows only: no process is asked or started, and the Restart Manager is a stub (test_pairing_roles' Case).
"""
from __future__ import annotations

from pathlib import Path
import os
import sys
import unittest
from unittest import mock

_HERE = str(Path(__file__).resolve().parent)
for entry in (str(Path(_HERE).parent / "src"), _HERE):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from codex_auto_resume import config  # noqa: E402
from codex_auto_resume.codex import layout, pairing  # noqa: E402
from codex_auto_resume.domain.ids import CODEX_APP_FAMILY  # noqa: E402
import test_pairing_roles as roles  # noqa: E402  (a module, so its cases are not bound here)

row, ENGINE = roles.row, roles.ENGINE
TRAMPOLINE = row(15, 10, roles.FOLDER + r"\app\Codex.exe", 150, CODEX_APP_FAMILY)
SERVER = row(20, 10, ENGINE, 200)


class TrampolineTests(roles.Case):
    def test_it_is_an_app_process_and_never_an_engine(self):
        self.assertTrue(pairing.app_process(TRAMPOLINE))
        self.assertFalse(pairing.engine_row(TRAMPOLINE))
        self.assertTrue(pairing.engine_row(SERVER))
        self.assertTrue(pairing.engine_row(row(31, 30, roles.FOLDER + r"\app\resources\codex.exe", 310)),
                        "the package's own engine, below the main's folder, is still one (#58)")

    def test_under_the_main_it_is_not_among_the_engines_the_app_serves(self):
        """Fails with the fix reverted: server_engines held the trampoline's path."""
        rows = [roles.MAIN, TRAMPOLINE, SERVER]
        self.assertEqual(pairing.server_engines(rows), frozenset({ENGINE}))
        self.assertEqual(pairing.engines_instead(rows, roles.OTHER_ENGINE), frozenset({ENGINE}))
        self.assertEqual(self.pair(rows, [self.held(SERVER)]), 20)
        found = layout.snapshot(rows, ENGINE, {"server_holds": True})
        self.assertEqual((found["engines_under_main"], found["helpers"], found["shape"]), (1, 1, "single_child"))

    def test_alone_under_the_main_it_is_no_server(self):
        rows = [roles.MAIN, TRAMPOLINE]
        self.assertEqual(pairing.server_engines(rows), frozenset())
        self.assertEqual(self.pair(rows, [self.held(TRAMPOLINE)], engine=TRAMPOLINE["path"]),
                         "desktop_server_missing_or_ambiguous")
        self.assertFalse(pairing.session_kind(rows, self.held(TRAMPOLINE), TRAMPOLINE["path"]))

    def test_discovery_never_runs_it(self):
        """What the watcher hands discovery (`app_engines`) never includes it, so `compatible` never runs it."""
        rows = [roles.MAIN, TRAMPOLINE, SERVER]
        ran = []

        def compatible(path):
            ran.append(str(path))
            raise RuntimeError("engine_not_found")

        with mock.patch.object(config, "candidate_codex_exes", return_value=[]), \
                mock.patch.dict(os.environ, {config.ENV_CODEX_EXE: ""}):
            with self.assertRaises(config.ConfigError):
                config.discover_codex_exe(None, compatible, running=lambda: pairing.server_engines(rows),
                                          ask_app_if_none=True)
        self.assertEqual(ran, [ENGINE])


if __name__ == "__main__":
    unittest.main()
