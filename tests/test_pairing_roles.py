"""The pairing takes the app's server by its role, not by the shape of the process list (v0.6.26).

Update resilience #2, #4, #5 and #9 (the owner's approval of 2026-11-22), closing audit-core C1 (= audit-security S1):

- #2 (i) a parent created after its child is not its parent: a TUI whose shell ended, its pid since given to a helper of
  the app, is not the app's (it was paired as the app's server where the app's own was between restarts);
- #2 (ii) any process of the app's package may sit between the main and its server, whatever it is called;
- #2 (iii) even one candidate must hold Codex's newest database where a Codex engine holds one, and another codex.exe
  the app runs holding one makes the pairing ambiguous;
- #2 (iv) "another session" only while the paired server holds Codex's databases;
- #4 a home with no thread-writer-locks folder while the app is paired reads unknown, never notLoaded;
- #5 the app main is known by its package family, not by the file name ChatGPT.exe;
- #9 a named engine that is not the app's says so (`Backend.app_unmatched_reason`).

Fixture rows only, as the inventory lists them since v0.6.26 (a creation time and a package family on each row): no
process is read and none is started, but for one look at this test's own process.
"""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from codex_auto_resume import windows as w
from codex_auto_resume.codex import pairing, transport
from codex_auto_resume.domain.ids import CODEX_APP_FAMILY

THREAD = "0a1b2c3d-0001-7000-8000-000000000001"
NATIVE = r"C:\Program Files"
FOLDER = NATIVE + r"\WindowsApps\OpenAI.Codex_26.1117.4957.0_x64__2p2nqsd0c76g0"
PACKAGE = FOLDER + r"\app\ChatGPT.exe"
ENGINE = r"C:\FakeLocalAppData\OpenAI\Codex\bin\abcdef0123456789\codex.exe"
OTHER_ENGINE = r"C:\FakeLocalAppData\OpenAI\Codex\bin\fedcba9876543210\codex.exe"
SHELL = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"


def row(pid, parent, path, created, family=None):
    return {"pid": pid, "parent": parent, "path": path, "created": created, "family": family}


MAIN = row(10, 1, PACKAGE, 100, CODEX_APP_FAMILY)
RENDERER = row(12, 10, PACKAGE, 120, CODEX_APP_FAMILY)


class Case(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        for name in ("state_5.sqlite", "queue_1.sqlite"):
            (self.home / name).write_bytes(b"")
        self.rows = []
        for stub in (patch.dict(os.environ, {"ProgramW6432": NATIVE}),
                     patch.object(pairing, "process_identity", side_effect=self.identity)):
            stub.start()
            self.addCleanup(stub.stop)

    def identity(self, pid):
        for each in self.rows:
            if each["pid"] == pid:
                return {"pid": pid, "created": each["created"], "path": each["path"].lower()}
        raise w.AdapterError("process_exited")

    def pair(self, rows, holders, engine=ENGINE):
        """The paired server's pid, or the error's code."""
        self.rows = rows
        with patch.object(pairing, "resource_users", return_value=holders):
            try:
                return w.desktop_pair(rows, Path(engine), self.home)["server"]["pid"]
            except w.AdapterError as error:
                return str(error)

    @staticmethod
    def held(each):
        return {"pid": each["pid"], "created": each["created"]}


class ReusedParentTests(Case):
    """#2 (i), audit-core C1's rows: main 10 (created 100); a TUI of the bundled engine, 40, started at 400 from a shell
    that ended; the app's utility process, started at 900, given the shell's old id 999. No app server is listed."""

    UTILITY = row(999, 10, PACKAGE, 900, CODEX_APP_FAMILY)
    TUI = row(40, 999, ENGINE, 400)

    def test_a_child_older_than_its_listed_parent_is_not_under_the_app(self):
        """Fails with the rule reverted: True, and the TUI was the app's."""
        rows = [MAIN, RENDERER, self.UTILITY, self.TUI]
        self.assertFalse(pairing.under_app(rows, self.TUI, 10))
        self.assertTrue(pairing.under_app(rows, row(41, 999, ENGINE, 950), 10), "a child the helper started is")

    def test_the_tui_is_not_paired_and_is_another_session(self):
        """Fails with the rule reverted: the TUI paired as the app's server, and loaded() said "loaded"."""
        rows = [MAIN, RENDERER, self.UTILITY, self.TUI]
        self.assertEqual(self.pair(rows, []), "desktop_server_missing_or_ambiguous")
        self.assertEqual(self.pair(rows, [self.held(self.TUI)]), "desktop_server_missing_or_ambiguous")
        self.assertTrue(pairing.session_kind(rows, self.held(self.TUI), ENGINE))
        self.assertEqual(pairing.server_engines(rows), frozenset())

    def test_a_time_that_could_not_be_read_breaks_the_chain(self):
        for utility in (dict(self.UTILITY, created=None), {k: v for k, v in self.UTILITY.items() if k != "created"}):
            with self.subTest(utility=utility):
                server = row(20, 999, ENGINE, 950)
                self.assertFalse(pairing.under_app([MAIN, utility, server], server, 10))

    def test_a_helper_older_than_the_main_whose_id_it_names_is_another_main(self):
        """A package process whose listed package parent was created after it lost its own parent: it is a main too,
        and two mains fail closed."""
        orphan = row(13, 10, PACKAGE, 50, CODEX_APP_FAMILY)
        self.assertEqual(len(pairing.app_mains([MAIN, orphan])), 2)
        with self.assertRaises(w.AdapterError):
            pairing._app_main([MAIN, orphan])


class PackageRoleTests(Case):
    """#2 (ii) and #5: a process of the app's package is the app's by its folder and its family, whatever it is
    called."""

    HELPER = row(11, 10, FOLDER + r"\app\Codex Helper.exe", 110, CODEX_APP_FAMILY)   # a renamed utility process
    SERVER = row(20, 11, ENGINE, 200)
    EXEC = row(21, 10, ENGINE, 210)

    def test_a_server_under_a_renamed_helper_holding_codex_state_is_paired(self):
        """Update resilience's probe 2: fails with the rule reverted - the helper was not the app's, the exec-server
        alone was paired, and the real server read as another session (#67 one rename away)."""
        rows = [MAIN, self.HELPER, self.SERVER, self.EXEC]
        self.assertTrue(pairing.under_app(rows, self.SERVER, 10))
        self.assertEqual(self.pair(rows, [self.held(self.SERVER)]), 20)
        self.assertFalse(pairing.session_kind(rows, self.held(self.SERVER), ENGINE))

    def test_a_renamed_main_is_the_main(self):
        """Update resilience's probe 3: fails with the rule reverted - no main, and "The Codex app is not running"."""
        main = row(10, 1, FOLDER + r"\app\OpenAI Codex.exe", 100, CODEX_APP_FAMILY)
        rows = [main, row(20, 10, ENGINE, 200)]
        self.assertEqual(pairing._app_main(rows)["pid"], 10)
        self.assertTrue(pairing.app_running(rows))
        self.assertEqual(self.pair(rows, []), 20)

    def test_the_family_alone_or_the_folder_alone_is_not_the_apps(self):
        """A process of the family outside the package's folder (a shell the app started may carry it) is no app
        process - a TUI under it stays another session - and a file in the folder that Windows says is of no family
        is not either, but the package's own ChatGPT.exe, as always."""
        shell = row(30, 10, SHELL, 300, CODEX_APP_FAMILY)
        tui = row(31, 30, ENGINE, 310)
        rows = self.rows = [MAIN, shell, tui]
        self.assertFalse(pairing.app_process(shell))
        self.assertFalse(pairing.under_app(rows, tui, 10))
        self.assertTrue(pairing.session_kind(rows, self.held(tui), ENGINE))
        self.assertFalse(pairing.app_process(row(11, 10, FOLDER + r"\app\Codex Helper.exe", 110)))
        self.assertTrue(pairing.app_process(row(11, 10, PACKAGE, 110)))
        self.assertFalse(pairing.app_process(row(11, 10, FOLDER + r"\app\..\..\x.exe", 110, CODEX_APP_FAMILY)))
        for name in ("codex.exe", "Codex.exe"):
            self.assertFalse(pairing.app_process(row(11, 10, FOLDER + "\\app\\resources\\" + name, 110,
                                                     CODEX_APP_FAMILY)), "an engine of the package is no app process")


class HolderTests(Case):
    """#2 (iii) and (iv)."""

    SERVER = row(20, 10, ENGINE, 200)
    TUI = row(30, 5, ENGINE, 300)

    def test_one_candidate_holding_nothing_beside_an_engine_that_holds_is_refused(self):
        """Fails with the rule reverted: the one candidate was paired without asking (#67's exec-server)."""
        app_server = row(22, 999, ENGINE, 220)          # under a helper the list does not show
        exec_server = row(21, 10, ENGINE, 210)
        rows = [MAIN, exec_server, app_server]
        self.assertEqual(self.pair(rows, [self.held(app_server)]), "desktop_server_missing_or_ambiguous")
        self.assertEqual(self.pair([MAIN, self.SERVER, self.TUI], [self.held(self.TUI)]),
                         "desktop_server_missing_or_ambiguous")

    def test_one_candidate_holding_or_no_engine_holding_is_paired(self):
        for holders in ([], [self.held(self.SERVER)], [self.held(self.SERVER), self.held(self.TUI)],
                        [{"pid": 77, "created": 1}], [{"pid": os.getpid(), "created": 1}]):
            with self.subTest(holders=holders):
                self.assertEqual(self.pair([MAIN, self.SERVER, self.TUI], holders), 20)

    def test_another_engine_of_the_app_holding_makes_it_ambiguous(self):
        """Fails with the rule reverted: the configured engine's one child was paired."""
        other = row(21, 10, OTHER_ENGINE, 210)
        rows = [MAIN, self.SERVER, other]
        self.assertEqual(self.pair(rows, [self.held(self.SERVER), self.held(other)]),
                         "desktop_server_missing_or_ambiguous")
        both = [MAIN, self.SERVER, row(23, 10, ENGINE, 230), other]
        self.assertEqual(self.pair(both, [self.held(self.SERVER), self.held(other)]),
                         "desktop_server_missing_or_ambiguous")
        self.assertEqual(self.pair(rows, [self.held(self.SERVER)]), 20)

    def test_the_pairing_says_whether_its_server_held_the_databases(self):
        self.rows = [MAIN, self.SERVER]
        for holders, holds in (([self.held(self.SERVER)], True), ([], False)):
            with self.subTest(holders=holders), patch.object(pairing, "resource_users", return_value=holders):
                seen = {}
                w.desktop_pair(self.rows, Path(ENGINE), self.home, seen=seen)
                self.assertEqual(seen, {"server_holds": holds})

    def backend(self, holders, lock_holders, folder=True):
        if folder:
            (self.home / "thread-writer-locks").mkdir(exist_ok=True)
        backend = w.Backend(self.home, Path(ENGINE))
        rows = [dict(each, path=str(backend.codex_exe)) if each["path"] == ENGINE else each
                for each in (MAIN, self.SERVER, self.TUI)]
        self.rows = rows
        with patch.object(backend, "_compatible"), patch.object(transport, "inventory", return_value=rows), \
                patch.object(pairing, "resource_users", return_value=holders), \
                patch.object(transport, "resource_users", return_value=lock_holders):
            identity = backend.app_identity()
            return backend, backend.loaded(THREAD, identity)

    def test_another_session_only_while_the_paired_server_holds_the_databases(self):
        """#2 (iv): fails with the rule reverted - "elsewhere" where the paired server held nothing."""
        backend, word = self.backend([self.held(self.SERVER)], [self.held(self.TUI)])
        self.assertEqual(word, "elsewhere")
        self.assertTrue(backend.server_holds)
        backend, word = self.backend([], [self.held(self.TUI)])
        self.assertEqual(word, "unknown")
        self.assertFalse(backend.server_holds)
        self.assertIsNone(backend.session_holder)

    def test_a_home_with_no_lock_folder_is_unknown_while_the_app_is_paired(self):
        """#4: fails with the rule reverted - "notLoaded", "The conversation is not open in the Codex app"."""
        backend, word = self.backend([self.held(self.SERVER)], [], folder=False)
        self.assertEqual(backend.app_look, "matched")
        self.assertEqual(word, "unknown")
        self.assertEqual(self.backend([self.held(self.SERVER)], [])[1], "notLoaded", "with the folder, as before")


class NamedEngineTests(Case):
    """#9: a named engine (--codex-exe, the setting, the environment) is never second-guessed; where the app runs another
    official engine the backend says why its server is unmatched."""

    def look(self, named, official=True):
        backend = w.Backend(self.home, Path(ENGINE))
        backend.named_engine = named
        rows = [MAIN, row(20, 10, OTHER_ENGINE, 200)]
        self.rows = rows
        with patch.object(backend, "_compatible"), patch.object(transport, "inventory", return_value=rows), \
                patch.object(transport, "official_engine", return_value=(official, "x")), \
                patch.object(pairing, "resource_users", return_value=[]):
            self.assertIsNone(backend.app_identity())
        return backend

    def test_a_named_engine_the_app_does_not_run_is_said(self):
        """Fails with the rule reverted: no attribute, plain app_server_unmatched."""
        backend = self.look(named=True)
        self.assertEqual(backend.app_look, "unmatched")
        self.assertEqual(backend.app_look_why, "named_engine")
        self.assertEqual(backend.app_unmatched_reason, transport.UNMATCHED_NAMED_ENGINE)
        self.assertEqual(transport.UNMATCHED_NAMED_ENGINE, "app_server_unmatched:named_engine")

    def test_otherwise_the_reason_is_the_one_it_always_was(self):
        for backend in (self.look(named=False), self.look(named=True, official=False)):
            with self.subTest():
                self.assertIsNone(backend.app_look_why)
                self.assertEqual(backend.app_unmatched_reason, "app_server_unmatched")


@unittest.skipUnless(os.name == "nt", "Windows only")
class InventoryTimeTests(unittest.TestCase):
    def test_each_row_carries_its_creation_time_and_family(self):
        """The Toolhelp read gives each row the creation time GetProcessTimes gives the process's own identity."""
        from codex_auto_resume.win import kernel
        rows = [each for each in kernel.processes_named(("python.exe",)) if each["pid"] == os.getpid()]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["created"], kernel.process_identity(os.getpid())["created"])
        self.assertIn("family", rows[0])


if __name__ == "__main__":
    unittest.main()
