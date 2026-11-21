"""Codex desktop 26.1117's app server is the app main's grandchild (v0.6.25, #67).

On Codex desktop 26.1117 the app's `codex.exe app-server` runs under a second ChatGPT.exe of the same package - the
`--type=utility` NodeService process, whose parent is the main - while `codex.exe exec-server` is still the main's own
child. The pairing took the app's server only among the main's children: it paired the exec-server, read the real
writer-lock holder as another Codex session, and every record waited `held_by_other_session` for ever.

A codex.exe now counts as the app's where every process between it and the main is one of the package's own
ChatGPT.exe processes (pairing.under_app) - in the pairing, in the served engines and in the other-session test alike.
Anything else in between (a shell, another program, a pid not listed, a loop) is not the app's. Of several such
servers, the one holding Codex's newest queue or state database (Restart Manager) is the app's, as with 26.930's two
children; the old layouts pair exactly as before. Fixture rows only: no process is read and none is started.
"""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from codex_auto_resume import windows as w
from codex_auto_resume.codex import pairing, transport

THREAD = "0a1b2c3d-0001-7000-8000-000000000001"
NATIVE = r"C:\Program Files"
PACKAGE = NATIVE + r"\WindowsApps\OpenAI.Codex_26.1117.4957.0_x64__2p2nqsd0c76g0\app\ChatGPT.exe"
FOREIGN_PACKAGE = NATIVE + r"\WindowsApps\OpenAI.Codex_26.1117.4957.0_x64__2p2nqsd0c76g0\app\ChatGPT.exe"
ENGINE = r"C:\FakeLocalAppData\OpenAI\Codex\bin\abcdef0123456789\codex.exe"
OTHER_ENGINE = r"C:\FakeLocalAppData\OpenAI\Codex\bin\fedcba9876543210\codex.exe"
SHELL = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"

MAIN = {"pid": 10, "parent": 1, "path": PACKAGE}
UTILITY = {"pid": 11, "parent": 10, "path": PACKAGE}          # --type=utility --utility-sub-type=node.mojom.NodeService
RENDERER = {"pid": 12, "parent": 10, "path": PACKAGE}
APP_SERVER = {"pid": 20, "parent": 11, "path": ENGINE}        # the grandchild: the one holding Codex's state
EXEC_SERVER = {"pid": 21, "parent": 10, "path": ENGINE}       # the main's own child


def layout_1117(*extra, exec_server=True):
    """The process rows Codex desktop 26.1117 runs, as the inventory lists them."""
    rows = [MAIN, UTILITY, RENDERER, APP_SERVER] + ([EXEC_SERVER] if exec_server else [])
    return [dict(row) for row in rows + list(extra)]


def layout_930(exec_server=True):
    """Codex 26.930's: the app server and the exec-server both the main's children; and the single-child one."""
    rows = [MAIN, dict(APP_SERVER, parent=10)] + ([EXEC_SERVER] if exec_server else [])
    return [dict(row) for row in rows]


class Case(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        for name in ("state_5.sqlite", "queue_1.sqlite"):
            (self.home / name).write_bytes(b"")
        self.identities = {pid: {"pid": pid, "created": pid * 10, "path": path.lower()}
                           for pid, path in ((10, PACKAGE), (11, PACKAGE), (12, PACKAGE), (20, ENGINE), (21, ENGINE),
                                             (30, SHELL), (31, ENGINE), (32, ENGINE), (52, ENGINE))}

        def identity(pid):
            if pid not in self.identities:
                raise w.AdapterError("process_exited")
            return dict(self.identities[pid])
        for stub in (patch.dict(os.environ, {"ProgramW6432": NATIVE}),
                     patch.object(pairing, "process_identity", side_effect=identity)):
            stub.start()
            self.addCleanup(stub.stop)

    def pair(self, rows, holders, **options):
        """(the paired server's pid or the error's code, the Restart Manager stub)."""
        with patch.object(pairing, "resource_users", return_value=holders) as users:
            try:
                return w.desktop_pair(rows, Path(ENGINE), self.home, **options)["server"]["pid"], users
            except w.AdapterError as error:
                return str(error), users

    def held(self, pid):
        return {"pid": pid, "created": self.identities[pid]["created"]}


class Layout1117Tests(Case):
    def test_the_grandchild_holding_codex_state_is_paired(self):
        """(a) Fails with the old rule: only the exec-server was a candidate, and it was paired."""
        pair, users = self.pair(layout_1117(), [self.held(20)])
        self.assertEqual(pair, 20)
        users.assert_called_once_with(self.home / "queue_1.sqlite", self.home / "state_5.sqlite")

    def test_two_holders_or_none_still_fail_closed(self):
        """(a) Fails with the old rule: the exec-server alone was paired without asking who holds the state."""
        for holders in ([], [self.held(20), self.held(21)], [{"pid": 77, "created": 1}]):
            with self.subTest(holders=holders):
                self.assertEqual(self.pair(layout_1117(), holders)[0], "desktop_server_missing_or_ambiguous")

    def test_the_app_server_is_not_another_session(self):
        """(a) Fails with the old rule: the real lock holder read as another Codex session."""
        rows = layout_1117()
        self.assertFalse(pairing.session_kind(rows, self.held(20), ENGINE))
        self.assertFalse(pairing.session_kind(rows, self.held(21), ENGINE))

    def test_a_configured_engine_under_anything_else_is_another_session(self):
        """(a) A shell between it and the app - even a shell the app's utility process started - or a parent the rows do
        not list leaves it another session; the app server beside them is still not one."""
        shell = {"pid": 30, "parent": 11, "path": SHELL}
        under_shell = {"pid": 31, "parent": 30, "path": ENGINE}
        orphan = {"pid": 32, "parent": 999, "path": ENGINE}
        rows = layout_1117(shell, under_shell, orphan)
        self.assertTrue(pairing.session_kind(rows, self.held(31), ENGINE))
        self.assertTrue(pairing.session_kind(rows, self.held(32), ENGINE))
        self.assertFalse(pairing.session_kind(rows, self.held(20), ENGINE))
        pair, _ = self.pair(rows, [self.held(20)])
        self.assertEqual(pair, 20)

    def test_the_grandchild_alone_is_paired(self):
        """(b) Fails with the old rule: no child of the main ran the engine."""
        for options in ({}, {"require_holder": True}):
            with self.subTest(options=options):
                pair, users = self.pair(layout_1117(exec_server=False), [self.held(20)], **options)
                self.assertEqual(pair, 20)
                self.assertEqual(users.called, bool(options), "one candidate is asked of only where a holder is required")
        self.assertFalse(pairing.session_kind(layout_1117(exec_server=False), self.held(20), ENGINE))

    def test_the_served_engines_see_the_grandchild(self):
        """(c) Fails with the old rule: the watcher's and the compatibility readers' served engines missed it."""
        moved = layout_1117(exec_server=False)
        moved[3]["path"] = OTHER_ENGINE
        self.assertEqual(pairing.server_engines(moved), frozenset({OTHER_ENGINE}))
        self.assertEqual(pairing.engines_instead(moved, ENGINE), frozenset({OTHER_ENGINE}))
        both = layout_1117()
        both[3]["path"] = OTHER_ENGINE
        self.assertEqual(pairing.server_engines(both), frozenset({OTHER_ENGINE, ENGINE}))
        self.assertEqual(pairing.engines_instead(both, ENGINE), frozenset())
        self.assertEqual(pairing.engines_instead(layout_1117(exec_server=False), OTHER_ENGINE), frozenset({ENGINE}))
        with patch.object(pairing, "inventory", return_value=layout_1117(exec_server=False)):
            self.assertEqual(pairing.app_engines(), frozenset({ENGINE}))

    def test_the_backend_reads_the_grandchild_holding_the_lock_as_loaded(self):
        """Fails with the old rule: the app's lock holder read "elsewhere", the record waiting held_by_other_session."""
        backend = w.Backend(self.home, Path(ENGINE))
        rows = [dict(row, path=str(backend.codex_exe)) if row["path"] == ENGINE else row for row in layout_1117()]
        for pid in (20, 21):
            self.identities[pid]["path"] = str(backend.codex_exe).lower()
        with patch.object(backend, "_compatible"), \
                patch.object(transport, "inventory", return_value=rows), \
                patch.object(pairing, "resource_users", return_value=[self.held(20)]), \
                patch.object(transport, "resource_users", return_value=[self.held(20)]):
            identity = backend.app_identity()
            self.assertEqual(identity["server"]["pid"], 20)
            self.assertEqual(backend.app_look, "matched")
            self.assertEqual(backend.loaded(THREAD, identity), "loaded")
            self.assertIsNone(backend.session_holder)


class NotTheAppsTests(Case):
    def test_a_package_process_outside_this_main_does_not_count(self):
        """(d) Fails with the old rule (no grandchild was paired): a codex.exe under package processes that never reach
        this main - their parents a loop - is not the app's, and the grandchild under the main still pairs alone."""
        loop = [{"pid": 50, "parent": 51, "path": FOREIGN_PACKAGE}, {"pid": 51, "parent": 50, "path": FOREIGN_PACKAGE}]
        foreign = {"pid": 52, "parent": 50, "path": ENGINE}
        rows = layout_1117(*loop, foreign, exec_server=False)
        pair, users = self.pair(rows, [self.held(52)])
        self.assertEqual(pair, 20)
        users.assert_not_called()
        self.assertTrue(pairing.session_kind(rows, self.held(52), ENGINE))
        self.assertFalse(pairing.session_kind(rows, self.held(20), ENGINE))
        rows[-1]["path"] = OTHER_ENGINE
        self.assertEqual(pairing.server_engines(rows), frozenset({ENGINE}))

    def test_another_program_in_between_does_not_count(self):
        """(d) A ChatGPT.exe outside the package, a pid the rows list twice, or a process that is its own parent between
        a codex.exe and the main is not the app's; the grandchild beside them still pairs alone (fails with the old
        rule)."""
        elsewhere = [{"pid": 40, "parent": 10, "path": r"C:\Elsewhere\ChatGPT.exe"}, {"pid": 41, "parent": 40,
                                                                                   "path": ENGINE}]
        twice = [{"pid": 42, "parent": 10, "path": PACKAGE}, {"pid": 42, "parent": 10, "path": SHELL},
                 {"pid": 43, "parent": 42, "path": ENGINE}]
        itself = [{"pid": 44, "parent": 44, "path": PACKAGE}, {"pid": 45, "parent": 44, "path": ENGINE}]
        for extra in (elsewhere, twice, itself):
            with self.subTest(extra=extra):
                rows = layout_1117(*extra, exec_server=False)
                self.assertEqual(pairing.server_engines(rows), frozenset({ENGINE}))
                self.assertEqual(self.pair(rows, [])[0], 20)
                self.assertFalse(pairing.under_app(rows, rows[-1], 10))
                self.assertTrue(pairing.under_app(rows, rows[3], 10))


class EveryLayoutTests(Case):
    def test_each_layout_pairs_the_server_holding_codex_state(self):
        """(e) 26.930's two children and the single child pair exactly as before; 26.1117's grandchild beside them
        (fails with the old rule)."""
        for name, rows, holders, asked in (("26.930 both children", layout_930(), [self.held(20)], True),
                                           ("one child", layout_930(exec_server=False), [], False),
                                           ("26.1117", layout_1117(), [self.held(20)], True),
                                           ("26.1117 server alone", layout_1117(exec_server=False), [], False)):
            with self.subTest(name):
                pair, users = self.pair(rows, holders)
                self.assertEqual(pair, 20)
                self.assertEqual(users.called, asked)
                self.assertFalse(pairing.session_kind(rows, self.held(20), ENGINE))
                self.assertEqual(pairing.server_engines(rows), frozenset({ENGINE}))

    def test_the_old_layouts_fail_closed_as_before(self):
        """(e) Two children both holding, or neither, still fail closed; a same-path codex.exe under another parent is
        another session, as it always was."""
        for holders in ([], [self.held(20), self.held(21)]):
            with self.subTest(holders=holders):
                self.assertEqual(self.pair(layout_930(), holders)[0], "desktop_server_missing_or_ambiguous")
        tui = {"pid": 31, "parent": 5, "path": ENGINE}
        rows = layout_930(exec_server=False) + [tui]
        self.assertTrue(pairing.session_kind(rows, self.held(31), ENGINE))
        self.assertEqual(self.pair(rows, [])[0], 20)
        # The grandchild case beside the old one, so the rule this module pins is the new one.
        self.assertTrue(pairing.under_app(layout_1117(), layout_1117()[3], 10))


if __name__ == "__main__":
    unittest.main()
