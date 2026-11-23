"""audit4 J1 / L1: a state read that fails at the store keeps the resident courier's roles, for UNREADABLE_FOR by the clock.

O2's fix kept the roles only where `Roles.wanted` RAISED, and its tests patched `Runtime.states` to raise. The real path
raises nothing: the state busy or locked past its timeout is a StateError that arming.read turns into every capability
OFF, marked failed (runtime._unreadable), so `follow` read "nothing is wanted", closed the server, journalled api.stopped
and ended the process - the 2026-11-19 ends. And the run was bounded by a count of reads taken as CHECK seconds each,
where a failed read can take 90-105 s: sixty of them lasted up to 100 minutes, not ten.

Here the store itself fails (`state.arming` raising StateError), and the resident's clock is the test's.

    CODEX_AR_EDITION=advanced PYTHONPATH="src;advanced/src;advanced/tests" python -m unittest test_advanced_resident_state_busy
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from codex_auto_resume_advanced.courier import resident  # noqa: E402
from codex_auto_resume_advanced.state.session import StateError  # noqa: E402
from test_advanced_resident import ResidentCase, _Server  # noqa: E402


class StateBusyTests(ResidentCase):
    def setUp(self):
        super().setUp()
        self.servers, self.clock = [], 1000.0

    def server(self, runtime, port, lan):
        self.servers.append(_Server())
        return self.servers[-1]

    def codes(self):
        return [line["code"] for line in self.rt.state.journal(capability="local_api")]

    def roles(self):
        self.assertTrue(self.arm(self.rt, "local_api")["done"])
        roles = resident.Roles(self.rt, server=self.server)
        roles._clock = lambda: self.clock
        self.assertTrue(roles.follow())
        return roles

    def busy(self):
        return patch.object(self.rt.state, "arming", side_effect=StateError("advanced state transaction failed"))

    def test_a_busy_state_keeps_the_server(self):
        """Fails with O2's fix alone: follow() False, the server closed, api.stopped journalled, api.unreadable never."""
        roles = self.roles()
        with self.busy():
            self.assertTrue(roles.follow())
        self.assertEqual(self.servers[0].closed, 0)
        self.assertNotIn("api.stopped", self.codes())
        self.assertEqual(self.codes().count("api.unreadable"), 1)
        self.assertTrue(roles.follow(), "read again: still on")
        self.assertEqual(len(self.servers), 1, "the same server, not a second")

    def test_slow_failed_reads_end_it_after_the_time_not_after_a_count(self):
        """Fails with the count: seven reads of 95 s each are 665 s by the clock but 70 s by reads times CHECK, so the
        run went on far past UNREADABLE_FOR. (The read raises here, as O2's own tests make it, so this proves the clock
        apart from the busy store.)"""
        roles = self.roles()
        with patch.object(self.rt, "states", side_effect=RuntimeError("slow, then failed")):
            for _read in range(7):
                self.assertTrue(roles.follow())
                self.clock += 95
            self.assertGreaterEqual(self.clock - 1000.0, resident.UNREADABLE_FOR)
            self.assertFalse(roles.follow(), "unreadable past UNREADABLE_FOR: nothing is served")
        self.assertEqual(self.servers[0].closed, 1)

    def test_within_the_time_fast_failed_reads_keep_it(self):
        roles = self.roles()
        with self.busy():
            for _read in range(resident.UNREADABLE_FOR // resident.CHECK - 1):
                self.assertTrue(roles.follow())
                self.clock += resident.CHECK
        self.assertEqual(self.servers[0].closed, 0)
        self.assertTrue(roles.follow())


if __name__ == "__main__":
    unittest.main()
