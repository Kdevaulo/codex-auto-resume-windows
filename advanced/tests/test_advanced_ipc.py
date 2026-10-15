"""The forced stop's channel to the Codex Desktop app, the codex-ipc pipe (v0.6.16-beta.4, item (h); MIPC passed): every
request's shape and pinned version, each answer the app gives turned into one closed word, the queue's resume behind
its seam, and a turn started after the reset - each against a scratch pipe of the test's own (fakeipc), never the
real one.

    PYTHONPATH=src;advanced/src python -m unittest discover -s advanced/tests -p test_advanced_ipc.py
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from codex_auto_resume_advanced.codex import ipc  # noqa: E402

THREAD = "019a0000-0000-7000-8000-00000000a001"
TURN = "019a0000-0000-7000-8000-00000000b002"


@unittest.skipUnless(sys.platform == "win32", "a Windows named pipe")
class StopTests(unittest.TestCase):
    def app(self, **script):
        import fakeipc
        found = fakeipc.FakeApp(script)
        self.addCleanup(found.close)
        return found

    def stop(self, app, turn=None):
        return ipc.stop_turn(THREAD, turn, channel=ipc.Channel(app.name))

    def test_a_stop_is_initialize_then_the_owner_then_the_stop_mode_system_to_that_owner(self):
        app = self.app()
        self.assertEqual(self.stop(app), (ipc.Stop.STOPPED, ipc.Resume.UNPROVEN))
        self.assertEqual([(method, version) for method, version, _params, _target in app.seen],
                         [("initialize", 0), ("thread-owner-discovery", 1), ("thread-follower-interrupt-turn", 3)])
        self.assertEqual(app.seen[1][2], {"hostId": "local", "conversationId": THREAD})
        self.assertEqual(app.seen[2][2:], ({"conversationId": THREAD, "mode": "system"}, "owner-client"))

    def test_knowing_the_running_turn_it_is_the_stop_that_names_it(self):
        app = self.app()
        self.stop(app, TURN)
        self.assertEqual(app.seen[2][:3], ("thread-follower-interrupt-turn", 4,
                                           {"conversationId": THREAD, "mode": "system", "expectedTurnId": TURN}))

    def test_each_failure_is_one_closed_word_and_nothing_waits_for_good(self):
        for script, word in (({"thread-owner-discovery": {"resultType": "error", "error": "no-client-found"}},
                              ipc.Stop.NO_CLIENT),
                             ({"thread-follower-interrupt-turn": {"resultType": "error",
                                                                  "error": "request-version-mismatch"}},
                              ipc.Stop.VERSION_MISMATCH),
                             ({"thread-follower-interrupt-turn": {"resultType": "error", "error": "whatever it says"}},
                              ipc.Stop.REFUSED),
                             ({"thread-follower-interrupt-turn": None}, ipc.Stop.NO_ANSWER)):
            with self.subTest(word=word), patch.object(ipc, "READ_SECONDS", 1.0):
                self.assertEqual(self.stop(self.app(**script)), (word, None))
        with patch.object(ipc, "PIPE", r"\\.\pipe\car-test-ipc-none-%d" % id(self)):
            self.assertEqual(ipc.stop_turn(THREAD), (ipc.Stop.NO_PIPE, None), "the app not running")

    def test_the_queue_is_put_back_only_once_its_request_is_measured(self):
        shape = (1, {"conversationId": "{thread}"})
        with patch.object(ipc, "QUEUE_RESUME", shape):
            app = self.app()
            self.assertEqual(self.stop(app), (ipc.Stop.STOPPED, ipc.Resume.RESUMED))
            self.assertEqual(app.seen[-1][:2], ("thread-follower-set-queued-follow-ups-state", 1))
            refused = self.app(**{"thread-follower-set-queued-follow-ups-state": {"resultType": "error",
                                                                                   "error": "no"}})
            self.assertEqual(self.stop(refused), (ipc.Stop.STOPPED, ipc.Resume.UNPROVEN))

    def test_a_turn_started_after_the_reset_carries_the_words(self):
        app = self.app()
        self.assertEqual(ipc.start_turn(THREAD, "Continue, please.", channel=ipc.Channel(app.name)), ipc.Start.STARTED)
        method, version, params, target = app.seen[-1]
        self.assertEqual((method, version, target), ("thread-follower-start-turn", 2, "owner-client"))
        self.assertEqual(params["turnStart"]["request"]["input"],
                         [{"type": "text", "text": "Continue, please.", "text_elements": []}])
        self.assertEqual(params["turnStart"]["request"]["threadId"], THREAD)
        gone = self.app(**{"thread-owner-discovery": {"resultType": "error", "error": "no-client-found"}})
        self.assertEqual(ipc.start_turn(THREAD, "x", channel=ipc.Channel(gone.name)), ipc.Stop.NO_CLIENT)

    def test_the_real_pipe_is_named_once_and_never_written_by_a_test(self):
        self.assertEqual(ipc.PIPE, r"\\.\pipe\codex-ipc")


if __name__ == "__main__":
    unittest.main()
