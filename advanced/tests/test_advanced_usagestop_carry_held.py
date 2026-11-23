"""v0.6.26 (audit4 B1): with usage_pause and reset_message both on, the person's reset message for a conversation the
forced stop stopped at the five-hour window is carried by the stop's turn once that window resets - even while the weekly
window still holds.

The stop's turn after the reset is the message's only route (review V1: reset_message leaves it to that turn, for the app
paused the conversation's queue). But `after_reset` returned at once while any window held (holding()), so with the weekly
window also over its stop percentage the turn never came: the message expired unsent a day after it fell due, its words
deleted, and at the weekly reset the product's own continuation went in its place. A person's message is never held by
the pause (UsagePause.holds); only the continuation itself waits for every window.

    CODEX_AR_EDITION=advanced PYTHONPATH="src;advanced/src;advanced/tests;tests" python -m unittest test_advanced_usagestop_carry_held
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_advanced_usagestop_carry import DAY, WORDS, CarryCase  # noqa: E402
from test_engine import T1  # noqa: E402

WEEK = 10080


class WeeklyHeldCase(CarryCase):
    def both_over(self, plug):
        """The five-hour window at 98 resetting in an hour, the weekly one at 98 resetting in three days."""
        self.weekly_reset = int(self.h.now) + 3 * DAY
        plug.runtime.state.save_meter([
            {"bucket": "codex", "window_minutes": 300, "used_percent": 98, "reset_at": self.reset},
            {"bucket": "codex", "window_minutes": WEEK, "used_percent": 98, "reset_at": self.weekly_reset}],
            at=self.h.now)

    def stopped_held(self):
        plug, turn = self.running()
        self.both_over(plug)
        self.h.tick(advance=61)
        self.h.tick(advance=61)
        (row,) = plug.runtime.state.continuations(capability=self.cap, pending=None)
        self.assertEqual((row["kind"], row["chain"]), ("after_reset", 300))
        return plug, turn

    def five_hour_reset(self, plug, turn):
        """The stopped turn ended; the five-hour window reset, the weekly one still over and held."""
        self.h.home.set_turn(T1, turn, status="interrupted", completed_at=int(self.h.now))
        self.h.now = self.reset + 120
        plug.runtime.state.save_meter([
            {"bucket": "codex", "window_minutes": 300, "used_percent": 1, "reset_at": self.reset + 5 * 3600},
            {"bucket": "codex", "window_minutes": WEEK, "used_percent": 98, "reset_at": self.weekly_reset}],
            at=self.h.now)

    def weekly_reset_passed(self, plug):
        self.h.now = self.weekly_reset + 120
        plug.runtime.state.save_meter([
            {"bucket": "codex", "window_minutes": 300, "used_percent": 1, "reset_at": int(self.h.now) + 5 * 3600},
            {"bucket": "codex", "window_minutes": WEEK, "used_percent": 1, "reset_at": int(self.h.now) + 7 * DAY}],
            at=self.h.now)


class CarriedWhileWeeklyHolds(WeeklyHeldCase):
    def test_the_message_goes_at_its_reset_while_the_weekly_window_holds(self):
        """Fails with B1 open: no start while the weekly window holds, the message expired a day on, its words gone,
        and the stop's own continuation sent at the weekly reset instead."""
        plug, turn = self.stopped_held()
        self.assertTrue(self.code(plug).holding())
        self.five_hour_reset(plug, turn)
        rule = self.rule(plug, state="ready", due_at=self.reset + 60)
        for _ in range(3):
            self.h.tick(advance=60)
        self.assertTrue(self.code(plug).holding(), "the weekly window still holds")
        self.assertEqual(self.starts, self.carried(), "one start, the person's words and their message's marker")
        self.assertEqual(self.h.backend.send_calls, [], "nothing into the queue the stop paused")
        self.assertEqual(self.rule_row(plug, rule), ("done", "delivered"))
        self.assertEqual(self.outcome(plug), "superseded")
        for _ in range(3):
            self.h.tick(advance=DAY / 2)
        self.weekly_reset_passed(plug)
        for _ in range(3):
            self.h.tick(advance=61)
        self.assertEqual(len(self.starts), 1, "nothing again at the weekly reset: no continuation beside the message")
        codes = self.journal(plug)
        self.assertIn("pause.message_instead", codes)
        self.assertNotIn("resetmsg.expired", codes)
        self.assertNotIn("pause.continued", codes)

    def test_without_a_message_the_continuation_still_waits_for_the_weekly_reset(self):
        """The continuation itself is the pause's own: held while any window holds, sent once at the weekly reset."""
        plug, turn = self.stopped_held()
        self.five_hour_reset(plug, turn)
        for _ in range(3):
            self.h.tick(advance=60)
        self.assertEqual(self.starts, [], "held with the weekly window")
        self.weekly_reset_passed(plug)
        for _ in range(3):
            self.h.tick(advance=61)
        self.assertEqual(len(self.starts), 1)
        self.assertFalse(self.starts[0][1].startswith(WORDS), "the stop's own continuation")
        self.assertIn("pause.continued", self.journal(plug))


if __name__ == "__main__":
    unittest.main()
