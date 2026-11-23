"""v0.6.26 third round O2 (the owner's logs): one failed read of the states no longer ends the resident courier.

`Roles.follow` read any exception from the states as "nothing is wanted": it closed the server, journalled api.stopped,
and the process ended; the watcher started it again 30 s on, and after three more in an hour gave up (api.gave_up) -
on 2026-11-19, during the slow state reads, the local API was down for the hour twice. Now what runs keeps running and
the read is tried again every CHECK seconds; a run of failed reads is journalled once ("unreadable"), so it can be told
from a person turning it off, and only UNREADABLE_FOR of them in a row end it.

    CODEX_AR_EDITION=advanced PYTHONPATH="src;advanced/src;advanced/tests" python -m unittest test_advanced_resident_unreadable
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from codex_auto_resume_advanced.courier import resident  # noqa: E402
from test_advanced_resident import ResidentCase, _Server  # noqa: E402


class UnreadableTests(ResidentCase):
    def setUp(self):
        super().setUp()
        self.servers = []

    def server(self, runtime, port, lan):
        self.servers.append(_Server())
        return self.servers[-1]

    def codes(self):
        return [line["code"] for line in self.rt.state.journal(capability="local_api")]

    def test_one_failed_read_keeps_the_server(self):
        """Fails with the old rule: the server closed, api.stopped journalled, and follow() False ended the process."""
        self.assertTrue(self.arm(self.rt, "local_api")["done"])
        roles = resident.Roles(self.rt, server=self.server)
        self.assertTrue(roles.follow())
        with patch.object(self.rt, "states", side_effect=RuntimeError("busy")):
            self.assertTrue(roles.follow())
        self.assertEqual(self.servers[0].closed, 0)
        self.assertNotIn("api.stopped", self.codes())
        self.assertTrue(roles.follow(), "read again: still on")
        self.assertEqual(len(self.servers), 1, "the same server, not a second")

    def test_a_run_of_failed_reads_is_journalled_once(self):
        """Fails without the code: nothing told a failed read from a turn-off."""
        self.assertTrue(self.arm(self.rt, "local_api")["done"])
        roles = resident.Roles(self.rt, server=self.server)
        roles.follow()
        with patch.object(self.rt, "states", side_effect=RuntimeError("busy")):
            for _check in range(5):
                roles.follow()
        self.assertEqual(self.codes().count("api.unreadable"), 1)
        roles.follow()
        with patch.object(self.rt, "states", side_effect=RuntimeError("busy")):
            roles.follow()
        self.assertEqual(self.codes().count("api.unreadable"), 2, "a new run, a new line")

    def test_a_reading_that_says_off_still_closes_at_once(self):
        self.assertTrue(self.arm(self.rt, "local_api")["done"])
        roles = resident.Roles(self.rt, server=self.server)
        roles.follow()
        with patch.object(self.rt, "states", side_effect=RuntimeError("busy")):
            roles.follow()
        self.rt.arming.disarm("local_api", actor="dashboard")
        self.assertFalse(roles.follow())
        self.assertEqual(self.servers[0].closed, 1)


if __name__ == "__main__":
    unittest.main()
