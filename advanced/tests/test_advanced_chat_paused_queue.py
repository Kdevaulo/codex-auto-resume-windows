"""A chat message in a queue the forced stop paused is never taken back (v0.6.26, finding M1 of the third audit).

usage_pause stops a conversation's running turn near a limit, and the app then pauses that conversation's queue until
the turn the stop's continuation after the reset starts has ended (engine/usagestop.py). A chat message sent there sits
in that queue, and the chat's own three-minute take-back used to delete it - its words gone, since the chat keeps none
once a message is sent (the owner's answer of 2026-10-11). Now a message that went into, or sat in, a queue the stop
paused is left with Codex, which runs it once it lets the queue go; it is never sent twice. A message sent after the
stop's continuation started is taken back after three minutes untaken, as before.

Held against the shipped definitions and core's own engine, store and simulated Codex home (takingcase.py).
"""
from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_advanced_chat as chat_case  # noqa: E402
from codex_auto_resume_advanced.engine import chat as chat_engine  # noqa: E402
from codex_auto_resume_advanced.registry import USAGE_METER, USAGE_PAUSE  # noqa: E402
from codex_auto_resume_advanced.vocabulary import ChatReason, ChatState, ContinuationReason  # noqa: E402
from test_engine import T1  # noqa: E402

DAY = 86400


class ChatInPausedQueueTests(chat_case.ChatCase):
    BESIDE = (USAGE_METER, USAGE_PAUSE)

    def stopped(self, plug):
        """usage_pause stopped T1's turn: its continuation after the reset kept, as the stop keeps it (`_remember`)."""
        pause = plug.runtime._code_of(USAGE_PAUSE)
        window = {"bucket": "codex", "minutes": 10080, "reset_at": int(self.h.now) + 3 * DAY}
        self.assertTrue(pause._remember(T1, SimpleNamespace(ordinal=1), window))
        return pause

    def sent(self, plug):
        key = self.waiting(plug)
        self.h.tick()
        self.assertEqual(len(self.h.home.queued(T1)), 1)
        self.assertEqual(plug.runtime.state.chat_by_record(key)["state"], ChatState.IN_FLIGHT)
        return key

    def test_one_in_a_queue_the_stop_paused_is_left_with_codex_and_runs_when_it_goes(self):
        """Fails without the forced stop's pause read: three minutes on it is taken back, its words gone."""
        plug = self.armed()
        pause = self.stopped(plug)
        key = self.sent(plug)
        queued = list(self.h.home.queued(T1))
        for _ in range(10):
            self.h.tick(advance=60)
        for _ in range(4):
            self.h.tick(advance=DAY / 2)                     # two days to the reset: Codex holds it all along
        self.assertEqual(self.h.home.queued(T1), queued, "still in Codex's queue")
        self.assertEqual(self.h.backend.deleted, [], "nothing deleted")
        row = plug.runtime.state.chat_by_record(key)
        self.assertEqual((row["state"], row["reason"]), (ChatState.IN_FLIGHT, None), "neither taken back nor unproven")
        pause._scoped.continuations.end(ContinuationReason.SENT, thread_id=T1)   # the turn after the reset started
        self.h.tick(advance=600)
        self.assertEqual(self.h.home.queued(T1), queued, "still not taken back while that turn runs")
        self.h.home.dispatch(T1)                              # it ended, and the app sends what was queued
        self.h.tick(advance=2)
        row = plug.runtime.state.chat_by_record(key)
        self.assertEqual((row["state"], row["reason"]), (ChatState.DONE, ChatReason.DELIVERED))
        self.assertEqual(len(self.calls), 1, "sent once")

    def test_one_sent_after_the_stops_continuation_started_is_taken_back_as_before(self):
        plug = self.armed()
        pause = self.stopped(plug)
        pause._scoped.continuations.end(ContinuationReason.SENT, thread_id=T1)
        self.h.now += 60
        key = self.sent(plug)
        for _ in range(4):
            self.h.tick(advance=60)
        row = plug.runtime.state.chat_by_record(key)
        self.assertEqual((row["state"], row["reason"]), (ChatState.CANCELLED, ChatReason.NOT_TAKEN))
        self.assertEqual(self.h.home.queued(T1), [])

    def test_what_reads_the_stop(self):
        row = {"thread_id": T1, "sent_at": 1000.0}
        stop = {"capability": "usage_pause", "kind": "after_reset", "thread_id": T1, "finished_at": None}
        self.assertTrue(chat_engine.paused_by_stop(row, [stop]), "waiting: the queue is paused")
        self.assertTrue(chat_engine.paused_by_stop(row, [dict(stop, finished_at=1000.0)]), "started after it was sent")
        self.assertFalse(chat_engine.paused_by_stop(row, [dict(stop, finished_at=999.0)]), "started before it was sent")
        self.assertFalse(chat_engine.paused_by_stop(row, [dict(stop, thread_id="other")]))
        self.assertFalse(chat_engine.paused_by_stop(row, [dict(stop, kind="keep_going")]), "another kind of continuation")
        self.assertFalse(chat_engine.paused_by_stop(row, [dict(stop, capability="usage_wrap_up")]),
                         "the wrap-up's continuation after a reset stopped nothing")
        self.assertFalse(chat_engine.paused_by_stop(row, ()))


if __name__ == "__main__":
    unittest.main()
