"""A message sent at a reset, and the moves of v0.6.15-beta (the owner's answer 6): its queue item kept, a Cancel of one
already in Codex's queue asking core to take it back, and HANDED_OVER, SUPERSEDED, WITHDRAWN and WITHDRAW_REFUSED each
ending it - or, refused, leaving it where it is - and none of them turning reset_message off.

    PYTHONPATH=src python -m unittest discover -s advanced/tests
"""
from __future__ import annotations

import contextlib
from pathlib import Path
import sqlite3
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import advancedcase as ac  # noqa: E402
from test_advanced_state import StateCase  # noqa: E402
from codex_auto_resume.domain import plughands  # noqa: E402
from codex_auto_resume_advanced.engine.resetmessage import handed  # noqa: E402
from codex_auto_resume_advanced.state import Refused  # noqa: E402
from codex_auto_resume_advanced.vocabulary import RecordState, Refusal, RuleReason, RuleState  # noqa: E402

QUEUE = "0a1b2c3d-0004-7000-8000-000000000004"


class MovesTests(StateCase):
    WORDS = "Pick up the migration where it stopped."

    def message(self, state, thread=ac.THREAD):
        key = "%064x" % (len(state.reset_rules(pending=None)) + 7)
        return state.add_reset_rule("reset_message", "codex", 300, 1, thread_id=thread, words=self.WORDS, record_id=key)

    def sent(self, state=None, thread=ac.THREAD):
        """A message claimed, launched and sent: what P14 SENT leaves, with the queue item Codex took it as."""
        state = state or self.state()
        rule = self.message(state, thread)
        key = state.reset_rule(rule)["record_id"]
        with contextlib.closing(sqlite3.connect(state.path)) as connection:
            connection.execute("UPDATE reset_rules SET state=? WHERE rule_id=?", (RuleState.READY, rule))
            connection.execute("UPDATE records SET state=?, claimed_at=? WHERE record_id=?",
                               (RecordState.IN_FLIGHT, self.now, key))
            connection.commit()
        moved = state.record_moved(key, "sent", at=self.now, queue_id=QUEUE)
        self.assertEqual(moved, {"capability": "reset_message", "trip": False})
        return state, rule, key

    def test_what_core_is_handed_of_a_message_in_flight_carries_its_queue_item(self):
        state, rule, key = self.sent()
        found = handed(state.reset_rule(rule))
        self.assertEqual((found["purpose"], found["ordinal"], found["queue_id"], found["withdraw"]),
                         ("message", None, QUEUE, False))
        self.assertEqual(plughands.records_of([found])[0]["queue_id"], QUEUE, "core takes it")

    def test_a_cancel_of_one_already_queued_asks_core_to_take_it_back(self):
        state, rule, key = self.sent()
        self.assertEqual(state.cancel_reset_rule(rule, at=self.now), "withdrawing")
        self.assertTrue(handed(state.reset_rule(rule))["withdraw"])
        self.assertEqual(state.reset_rule(rule)["state"], RuleState.READY, "still in flight until core says")
        state.record_moved(key, "withdrawn", at=self.now)
        found = state.reset_rule(rule)
        self.assertEqual((found["state"], found["reason"], found["record_state"]),
                         (RuleState.CANCELLED, RuleReason.WITHDRAWN, RecordState.CANCELLED))

    def test_one_codex_would_not_give_back_is_left_where_it_is_and_said(self):
        state, rule, key = self.sent()
        state.cancel_reset_rule(rule, at=self.now)
        moved = state.record_moved(key, "withdraw_refused", at=self.now)
        self.assertFalse(moved["trip"])
        found = state.reset_rule(rule)
        self.assertEqual((found["state"], found["reason"], found["record_state"], found["withdraw"]),
                         (RuleState.READY, RuleReason.WITHDRAW_REFUSED, RecordState.IN_FLIGHT, False))

    def test_handed_over_and_superseded_end_it_and_trip_nothing(self):
        state = self.state()
        for n, (move, reason) in enumerate((("handed_over", RuleReason.HANDED_OVER),
                                            ("superseded", RuleReason.SUPERSEDED))):
            with self.subTest(move):
                state, rule, key = self.sent(state, thread="0a1b2c3d-0001-7000-8000-%012d" % (100 + n))
                moved = state.record_moved(key, move, at=self.now)
                self.assertFalse(moved["trip"])
                found = state.reset_rule(rule)
                self.assertEqual((found["state"], found["reason"], found["words"]), (RuleState.DONE, reason, None))

    def test_one_not_yet_launched_is_cancelled_at_once_and_one_launching_is_refused(self):
        state = self.state()
        rule = self.message(state)
        self.assertEqual(state.cancel_reset_rule(rule, at=self.now), "cancelled")
        state2, rule2, key2 = self.sent(state, thread="0a1b2c3d-0001-7000-8000-000000000200")
        with contextlib.closing(sqlite3.connect(state2.path)) as connection:
            connection.execute("UPDATE reset_rules SET sent_at=NULL, launching_at=? WHERE rule_id=?", (self.now, rule2))
            connection.commit()
        with self.assertRaises(Refused) as refused:
            state2.cancel_reset_rule(rule2, at=self.now)
        self.assertEqual(refused.exception.refusal, Refusal.BEING_SENT)


if __name__ == "__main__":
    unittest.main()
