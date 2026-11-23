"""With usage_pause and reset_message both on, the person's reset message for a conversation the forced stop stopped at
the five-hour window waits for EVERY window the stop holds to reset, and then the stop's own turn carries it, once
(review4 V1, the owner's answer of 2026-11-23).

audit4 B1: `after_reset` returned at once while any window held, so the message, left to the stop's turn, expired unsent
a day after it fell due and the stop's continuation went in its place at the weekly reset. B1's first fix carried it at
its own window's reset while the weekly window still held - a turn into a weekly window over its stop percentage, which
nothing stopped, and core's continuation after it at the weekly reset (review4 V1). Now no turn starts while a held
window holds; the message is kept - it never expires for that wait - and is carried at the weekly reset, with no
continuation beside it.

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
    def test_the_message_waits_for_the_weekly_reset_and_goes_once_then(self):
        """Fails with B1's first fix (carried at the five-hour reset while the weekly window holds) and with B1 open
        (expired a day on, the continuation sent instead at the weekly reset)."""
        plug, turn = self.stopped_held()
        self.assertTrue(self.code(plug).holding())
        self.five_hour_reset(plug, turn)
        rule = self.rule(plug, state="ready", due_at=self.reset + 60)
        for _ in range(3):
            self.h.tick(advance=60)
        self.assertTrue(self.code(plug).holding(), "the weekly window still holds")
        self.assertEqual(self.starts, [], "no turn while the weekly window holds")
        self.assertEqual(self.h.backend.send_calls, [], "nothing into the queue the stop paused")
        for _ in range(3):
            self.h.tick(advance=DAY / 2)
        self.assertEqual(self.starts, [])
        row = plug.runtime.state.reset_rule(rule)
        self.assertEqual((row["state"], row["words"]), ("ready", WORDS), "kept with its words, not expired")
        self.weekly_reset_passed(plug)
        for _ in range(3):
            self.h.tick(advance=61)
        self.assertEqual(self.starts, self.carried(), "one start at the weekly reset, the person's words and marker")
        self.assertEqual(self.h.backend.send_calls, [])
        self.assertEqual(self.rule_row(plug, rule), ("done", "delivered"))
        self.assertEqual(self.outcome(plug), "superseded")
        for _ in range(3):
            self.h.tick(advance=61)
        self.assertEqual(len(self.starts), 1, "no continuation beside the message")
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
