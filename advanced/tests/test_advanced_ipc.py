"""The forced stop's channel to the Codex Desktop app, the codex-ipc pipe (v0.6.16-beta.4, item (h); MIPC passed): every
request's shape and pinned version, each answer the app gives turned into one closed word, the queue's resume behind
its seam, and a turn started after the reset - each against a scratch pipe of the test's own (fakeipc), never the
real one.

    PYTHONPATH=src;advanced/src python -m unittest discover -s advanced/tests -p test_advanced_ipc.py
"""
from __future__ import annotations

from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from codex_auto_resume_advanced.codex import ipc  # noqa: E402

THREAD = "aaaaaaaa-0000-7000-8000-00000000a001"
TURN = "bbbbbbbb-0000-7000-8000-00000000b002"


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
        self.assertEqual(self.stop(app), ipc.Stop.STOPPED)
        self.assertEqual([(method, version) for method, version, _params, _target in app.seen],
                         [("initialize", 0), ("thread-owner-discovery", 1), ("thread-follower-interrupt-turn", 3)])
        self.assertEqual(app.seen[1][2], {"hostId": "local", "conversationId": THREAD})
        self.assertEqual(app.seen[2][2:], ({"conversationId": THREAD, "mode": "system"}, "owner-client"))

    def test_knowing_the_running_turn_it_is_the_stop_that_names_it(self):
        app = self.app()
        self.stop(app, TURN)
        self.assertEqual(app.seen[2][:3], ("thread-follower-interrupt-turn", 4,
                                           {"conversationId": THREAD, "mode": "system", "expectedTurnId": TURN}))

    def test_a_success_counts_as_a_stop_only_when_it_names_the_turn_it_stopped(self):
        """MIPC-v4 (codex-cli 0.163, app 26.1013): v4 with a stale or made-up expectedTurnId answers success with no
        interruptedTurnId and the turn runs on - a silent no-op, never counted as a stop."""
        app = self.app()
        app.running = TURN
        self.assertEqual(self.stop(app, TURN), ipc.Stop.STOPPED, "the right turn: stopped")
        stale = self.app()
        stale.running = TURN
        self.assertEqual(self.stop(stale, "cccccccc-0000-7000-8000-00000000c003"), ipc.Stop.NOT_STOPPED,
                         "a stale turn: success naming none, nothing stopped")
        for result in ({}, {"interruptedTurnId": ""}, {"interruptedTurnId": "another"}, None):
            with self.subTest(result=result):
                named = self.app(**{"thread-follower-interrupt-turn": {"resultType": "success", "result": result}})
                self.assertEqual(self.stop(named, TURN), ipc.Stop.NOT_STOPPED)
        for result, word in (({"interruptedTurnId": "any"}, ipc.Stop.STOPPED), ({}, ipc.Stop.NOT_STOPPED)):
            with self.subTest(v3=result):
                named = self.app(**{"thread-follower-interrupt-turn": {"resultType": "success", "result": result}})
                self.assertEqual(self.stop(named), word, "v3, no turn known: any turn named is the stop")

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
                self.assertEqual(self.stop(self.app(**script)), word)
        with patch.object(ipc, "PIPE", r"\\.\pipe\car-test-ipc-none-%d" % id(self)):
            self.assertEqual(ipc.stop_turn(THREAD), ipc.Stop.NO_PIPE, "the app not running")

    def test_nothing_is_asked_of_the_queue(self):
        """Measured 2026-10-16: the turn started after the reset is what lets the paused queue go - the stop asks the
        app for nothing more than the stop."""
        app = self.app()
        self.stop(app)
        self.assertNotIn("thread-follower-set-queued-follow-ups-state", [seen[0] for seen in app.seen])
        self.assertFalse(hasattr(ipc, "QUEUE_RESUME"))

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


class _Channel:
    """A channel with no pipe: what it is written is kept, and each read gives the next frame `frames` makes after
    `every` seconds."""

    def __init__(self, frames, every=0.0):
        self.frames, self.every, self.written = frames, every, []

    def write(self, message):
        self.written.append(message)

    def read(self, seconds=None):
        time.sleep(self.every)
        return self.frames(self.written[-1])

    def close(self):
        pass


def _broadcast(_request):
    return {"type": "broadcast", "method": "thread-stream-state-changed", "params": {}}


class DeadlineTests(unittest.TestCase):
    """Each request has one deadline for its whole answer, and frames that are not the answer do not use it up."""

    def test_a_trickle_of_broadcasts_never_stretches_a_request_past_its_deadline(self):
        channel = _Channel(_broadcast, every=0.25)
        began = time.monotonic()
        with patch.object(ipc, "READ_SECONDS", 1.0):
            self.assertEqual(ipc.stop_turn(THREAD, TURN, channel=channel), ipc.Stop.NO_ANSWER)
        self.assertLess(time.monotonic() - began, 2.5, "one deadline, not one per frame")

    def test_many_broadcasts_before_the_answer_still_reach_it(self):
        counts = {}

        def frames(request):
            seen = counts.setdefault(request["requestId"], [0])
            seen[0] += 1
            if seen[0] <= 25:
                return _broadcast(request)
            result = {"initialize": {"clientId": "c"}, "thread-follower-interrupt-turn": {"interruptedTurnId": TURN}}
            return {"type": "response", "requestId": request["requestId"], "resultType": "success",
                    "result": result.get(request["method"], {}), "handledByClientId": "owner"}
        self.assertEqual(ipc.stop_turn(THREAD, TURN, channel=_Channel(frames)), ipc.Stop.STOPPED)


if __name__ == "__main__":
    unittest.main()
