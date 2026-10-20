"""v0.6.17: what Diagnostics says of where the watcher and the Dashboard's bridge run.

* Inside another app: a process descended from an MSIX app - the Codex app, Claude desktop - writes HKCU and
  %APPDATA% into that app's private view, and may end when that app closes. The bridge asks win/kernel.py's walk
  (held guard by guard in tests/test_host_app.py PythonWalkTests) of the watcher's process, named by its heartbeat
  and held to the time it says it started, and of its own; `host-app` gives both back, a package family name at
  most. Here the control method and the bridge, with the walk stood in for: no live process is asked, so the answer
  is the same inside Claude on this laptop and inside nothing on CI.
* The state folder and Codex's sandbox: Codex's Windows sandbox adds an explicit `(OI)(CI)(RX)` entry for its local
  group CodexSandboxUsers to a user's folders. win/acl.py says that apart - CODEX_SANDBOX, a line naming the group -
  while every entry for the group only reads; another account beside it, or the group with any right to write,
  keeps the other-accounts warning. Held over security descriptors written as SDDL and read in this process
  (acl.described_entries), with the account lookup stood in for: no folder's access list is read or changed.
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from codex_auto_resume import control, controlcli  # noqa: E402
from codex_auto_resume.win import kernel  # noqa: E402
from test_control import ControlTestCase  # noqa: E402

CODEX = "OpenAI.Codex_2p2nqsd0c76g0"
OUTSIDE = {"state": "outside", "family": None, "app": None}
INSIDE = {"state": "inside", "family": CODEX, "app": "OpenAI.Codex"}


class HostAppControlTests(ControlTestCase):
    """control.host_app: the watcher's part asked of the process its heartbeat names, only while it runs."""

    def asked(self, watcher, walk):
        calls = []

        def stand_in(pid=None, started_by=None):
            calls.append((pid, started_by))
            return dict(walk(pid))
        with patch.object(kernel, "host_app", side_effect=stand_in), \
                patch.object(control.Control, "_watcher", lambda self, store: watcher):
            return self.control.host_app(), calls

    def test_no_watcher_running_is_said_and_only_the_bridge_is_asked(self):
        answer, calls = self.asked({"running": False, "pid": 4242, "started_at": 1.0e9}, lambda pid: OUTSIDE)
        self.assertEqual(answer, {"watcher": {"state": "not_running", "family": None, "app": None}, "bridge": OUTSIDE})
        self.assertEqual(calls, [(None, None)], "a watcher that does not run is not looked for")

    def test_a_running_watcher_is_asked_by_its_heartbeats_id_and_start(self):
        answer, calls = self.asked({"running": True, "pid": 4242, "started_at": 1.0e9},
                                   lambda pid: INSIDE if pid == 4242 else OUTSIDE)
        self.assertEqual(answer, {"watcher": INSIDE, "bridge": OUTSIDE})
        self.assertIn((4242, 1.0e9), calls, "held to the time the watcher says it started")

    def test_a_running_watcher_without_an_id_or_a_start_is_unknown(self):
        for watcher in ({"running": True, "pid": None, "started_at": 1.0e9},
                        {"running": True, "pid": 4242, "started_at": None},
                        {"running": True, "pid": True, "started_at": 1.0e9},
                        {"running": None}):
            with self.subTest(watcher):
                answer, calls = self.asked(watcher, lambda pid: INSIDE)
                self.assertEqual(answer["watcher"]["state"], "unknown")
                self.assertEqual(calls, [(None, None)])

    def test_the_bridge_gives_both_parts(self):
        with patch.object(kernel, "host_app", side_effect=lambda pid=None, started_by=None: dict(OUTSIDE)):
            reply = controlcli.dispatch(self.control, "host-app", {})
        self.assertEqual(reply, {"ok": True, "result": {
            "watcher": {"state": "not_running", "family": None, "app": None}, "bridge": OUTSIDE}})


# ----------------------------------------------------------------------- the state folder and Codex's sandbox
OWN = "S-1-5-21-1-2-3-1001"
GROUP = "S-1-5-21-1-2-3-1011"
OTHER = "S-1-5-21-1-2-3-1002"
COMPUTER = "EXAMPLE-PC"
# A folder as the installer leaves it: Windows, the administrators and this account, nothing inherited.
BASE = "D:PAI(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;FA;;;%s)" % OWN
# The entry Codex's Windows sandbox adds, as icacls shows it: CodexSandboxUsers:(OI)(CI)(RX).
SANDBOX_READ = "(A;OICI;0x1200a9;;;%s)" % GROUP


def accounts(group=("CodexSandboxUsers", COMPUTER, 4)):
    """Windows' answer for each identifier, stood in for: the sandbox group (or what `group` makes it), another
    person's account, and nothing for anything else."""
    table = {GROUP: group, OTHER: ("ExampleUser2", COMPUTER, 1)}
    return table.get


class SandboxReadTests(unittest.TestCase):
    def setUp(self):
        from codex_auto_resume.win import acl
        self.acl = acl

    def word(self, sddl, group=("CodexSandboxUsers", COMPUTER, 4), computer=COMPUTER):
        entries = self.acl.described_entries(sddl)
        self.assertIsNotNone(entries, sddl)
        return self.acl.verdict(entries, OWN, self.acl.sandbox_sids(entries, accounts(group), computer))

    def test_the_entry_is_read_with_its_rights(self):
        self.assertEqual(self.acl.described_entries(BASE + SANDBOX_READ)[-1], (GROUP, 0x1200A9))

    def test_the_sandbox_groups_read_entry_alone_is_said_as_what_it_is(self):
        self.assertEqual(self.word(BASE + SANDBOX_READ), "codex_sandbox")
        self.assertEqual(self.word(BASE + "(A;OICI;GRGX;;;%s)" % GROUP), "codex_sandbox", "generic read and execute")
        self.assertEqual(self.word(BASE), "owner_only", "without it, as before")

    def test_another_account_beside_it_keeps_the_warning(self):
        self.assertEqual(self.word(BASE + SANDBOX_READ + "(A;OICI;0x1200a9;;;%s)" % OTHER), "shared")
        self.assertEqual(self.word(BASE + SANDBOX_READ + "(A;OICI;GR;;;BU)"), "shared", "Users")

    def test_the_group_with_any_right_to_write_keeps_the_warning(self):
        for rights in ("0x1301bf", "FA", "GA", "GW", "WD", "SD"):
            with self.subTest(rights):
                self.assertEqual(self.word(BASE + "(A;OICI;%s;;;%s)" % (rights, GROUP)), "shared")
        self.assertEqual(self.word(BASE + SANDBOX_READ + "(A;;FW;;;%s)" % GROUP), "shared",
                         "a second entry for the group that writes")

    def test_a_refusal_for_the_group_lets_nobody_in(self):
        self.assertEqual(self.word(BASE + "(D;OICI;FA;;;%s)" % GROUP), "owner_only")

    def test_the_group_is_this_computers_local_group_by_name_whatever_the_computer_is_called(self):
        self.assertEqual(self.word(BASE + SANDBOX_READ, group=("codexsandboxusers", "other-pc", 4),
                                   computer="OTHER-PC"), "codex_sandbox")
        for group in (("CodexSandboxUsers", "CORP", 4), ("CodexSandboxUsers", COMPUTER, 1),
                      ("CodexSandboxUsersX", COMPUTER, 4)):
            with self.subTest(group):
                self.assertEqual(self.word(BASE + SANDBOX_READ, group=group), "shared")
        self.assertEqual(self.word(BASE + SANDBOX_READ, computer=""), "shared", "no computer name, no match")

    def test_the_folder_is_asked_and_the_group_looked_up_as_the_bridge_does(self):
        entries = self.acl.described_entries(BASE + SANDBOX_READ)
        with patch.object(self.acl, "allowed_entries", return_value=entries), \
                patch.object(self.acl, "_own_sid", return_value=OWN), \
                patch.object(self.acl, "_account", side_effect=accounts()), \
                patch.object(self.acl, "_computer", return_value=COMPUTER), \
                patch.object(self.acl.os, "name", "nt"):
            self.assertEqual(self.acl.state_access("C:\\not-read"), "codex_sandbox")
        with patch.object(self.acl, "allowed_entries", return_value=entries), \
                patch.object(self.acl, "_own_sid", return_value=OWN), \
                patch.object(self.acl, "_account", return_value=None), \
                patch.object(self.acl, "_computer", return_value=COMPUTER), \
                patch.object(self.acl.os, "name", "nt"):
            self.assertEqual(self.acl.state_access("C:\\not-read"), "shared", "a group Windows does not name")


class StateAccessBridgeTests(ControlTestCase):
    def test_the_bridge_says_the_word(self):
        from codex_auto_resume.win import acl
        with patch.object(acl, "state_access", return_value="codex_sandbox"):
            reply = controlcli.dispatch(self.control, "state-access", {})
        self.assertEqual(reply, {"ok": True, "result": {"access": "codex_sandbox"}})


if __name__ == "__main__":
    unittest.main()
