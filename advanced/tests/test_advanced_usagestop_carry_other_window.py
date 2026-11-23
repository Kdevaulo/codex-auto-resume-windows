"""audit4 B3 (the owner's answer of 2026-11-23, "carry it at the stop's own turn"): with usage_pause and reset_message both
on, a reset message written for the OTHER window than the one the forced stop stopped at is carried by the stop's own
turn after its reset too - never queued into the queue the stop paused.

`carried_by_stop` and `_message_instead` looked only at rules whose window was the stop's (`minutes == chain`), so a
message of the other window that fell due while the stop held was handed to core, which queued it into Codex's paused
queue: it sat there until the stop's window reset, and then the stop's own continuation went as well - both sent, the
message days late. Now any message of that conversation due since the stop waits for the stop's turn, which carries it
in the continuation's place: one start, the message's words, nothing in Codex's queue. And while it waits - days, for a
weekly stop - it does not expire (`_held_by_stop`).

Both directions: a weekly stop with a five-hour message, and a five-hour stop with a weekly message.

    CODEX_AR_EDITION=advanced PYTHONPATH="src;advanced/src;advanced/tests;tests" python -m unittest test_advanced_usagestop_carry_other_window
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_advanced_usagestop_reset_message as instead  # noqa: E402
from test_advanced_usagestop_carry import DAY, WORDS, CarryCase  # noqa: E402
from test_engine import T1  # noqa: E402

FIVE, WEEK = 300, 10080


class OtherWindowCase(CarryCase):
    def meter(self, plug, five, five_reset, week, week_reset):
        plug.runtime.state.save_meter([
            {"bucket": "codex", "window_minutes": FIVE, "used_percent": five, "reset_at": int(five_reset)},
            {"bucket": "codex", "window_minutes": WEEK, "used_percent": week, "reset_at": int(week_reset)}],
            at=self.h.now)

    def stopped_at(self, chain, five, week, week_in):
        """Stopped at window `chain`: the five-hour window at `five` resetting at self.reset (an hour on), the weekly
        at `week` resetting `week_in` seconds on (self.weekly_reset)."""
        plug, turn = self.running()
        self.weekly_reset = int(self.h.now) + week_in
        self.meter(plug, five, self.reset, week, self.weekly_reset)
        self.h.tick(advance=61)
        self.h.tick(advance=61)
        (row,) = plug.runtime.state.continuations(capability=self.cap, pending=None)
        self.assertEqual((row["kind"], row["chain"]), ("after_reset", chain))
        self.h.home.set_turn(T1, turn, status="interrupted", completed_at=int(self.h.now))
        return plug

    def message(self, plug, minutes, due_at):
        state = plug.runtime.state
        rule_id = state.add_reset_rule("reset_message", "codex", minutes, 1, thread_id=T1, words=WORDS,
                                       record_id=instead.RECORD, at=self.h.now)
        self.assertTrue(state.change_rule(rule_id, state="ready", due_at=int(due_at)))
        return rule_id

    def nothing_sent_yet(self, plug, rule):
        self.assertEqual(self.starts, [])
        self.assertEqual(self.h.backend.send_calls, [], "never handed to core")
        self.assertEqual(self.h.home.queued(T1), [], "nothing in the queue the stop paused")
        row = plug.runtime.state.reset_rule(rule)
        self.assertEqual((row["state"], row["words"]), ("ready", WORDS), "held with its words, not expired")

    def carried_once(self, plug, rule):
        self.assertEqual(self.starts, self.carried(), "one start, the person's words and their message's marker")
        self.assertEqual(self.h.backend.send_calls, [])
        self.assertEqual(self.h.home.queued(T1), [])
        self.assertEqual(self.rule_row(plug, rule), ("done", "delivered"))
        self.assertEqual(self.outcome(plug), "superseded")
        codes = self.journal(plug)
        self.assertNotIn("pause.continued", codes, "no continuation beside the message")
        self.assertNotIn("resetmsg.expired", codes)


class WeeklyStopFiveHourMessage(OtherWindowCase):
    def test_a_five_hour_message_waits_for_the_weekly_stop_s_turn_and_does_not_expire(self):
        """Fails with B3 open: at the five-hour reset core queues the message into the paused queue (send_calls 1), and
        at the weekly reset the stop's continuation goes beside it."""
        plug = self.stopped_at(WEEK, 50, 98, 3 * DAY)
        weekly_reset = self.weekly_reset
        self.h.now = self.reset + 120                                  # the five-hour window reset; the weekly holds
        self.meter(plug, 1, self.reset + 5 * 3600, 98, weekly_reset)
        rule = self.message(plug, FIVE, self.reset + 60)
        for _ in range(3):
            self.h.tick(advance=60)
        self.nothing_sent_yet(plug, rule)
        for _ in range(4):                                             # two days: past B1's day of expiry
            self.h.tick(advance=DAY / 2)
            self.meter(plug, 1, int(self.h.now) + 5 * 3600, 98, weekly_reset)
        self.nothing_sent_yet(plug, rule)
        self.h.now = weekly_reset + 120                                # the stop's own window resets
        self.meter(plug, 1, int(self.h.now) + 5 * 3600, 1, int(self.h.now) + 7 * DAY)
        for _ in range(3):
            self.h.tick(advance=61)
        self.carried_once(plug, rule)


class FiveHourStopWeeklyMessage(OtherWindowCase):
    def test_a_weekly_message_due_inside_the_five_hour_stop_is_carried_at_its_reset(self):
        """Fails with B3 open: at the weekly reset core queues the message into the paused queue, and at the five-hour
        reset the stop's continuation goes beside it."""
        plug = self.stopped_at(FIVE, 98, 50, 1800)
        weekly_reset = self.weekly_reset
        self.h.now = weekly_reset + 120                                # the weekly window reset inside the stop's hold
        self.meter(plug, 98, self.reset, 1, int(self.h.now) + 7 * DAY)
        rule = self.message(plug, WEEK, weekly_reset + 60)
        for _ in range(3):
            self.h.tick(advance=60)
        self.nothing_sent_yet(plug, rule)
        self.h.now = self.reset + 120                                  # the stop's own window resets
        self.meter(plug, 1, self.reset + 5 * 3600, 1, weekly_reset + 7 * DAY)
        for _ in range(3):
            self.h.tick(advance=61)
        self.carried_once(plug, rule)


class LetGoByTheStop(OtherWindowCase):
    def test_a_message_the_stop_let_go_counts_its_day_from_then(self):
        """Held two days, then usage_pause turned off, which ends its continuation: the message is not expired at once
        for the wait the stop made - its day counts from the hold's end - and it goes to core."""
        plug = self.stopped_at(WEEK, 50, 98, 3 * DAY)
        weekly_reset = self.weekly_reset
        self.h.now = self.reset + 120
        self.meter(plug, 1, self.reset + 5 * 3600, 98, weekly_reset)
        rule = self.message(plug, FIVE, self.reset + 60)
        for _ in range(4):
            self.h.tick(advance=DAY / 2)
            self.meter(plug, 1, int(self.h.now) + 5 * 3600, 98, weekly_reset)
        self.nothing_sent_yet(plug, rule)
        plug.runtime.arming.disarm(self.cap, actor="dashboard")
        for _ in range(3):
            self.h.tick(advance=60)
        self.assertNotIn("resetmsg.expired", self.journal(plug))
        self.assertEqual(len(self.h.backend.send_calls), 1, "handed to core once the stop let it go")
        self.assertEqual(self.starts, [])


if __name__ == "__main__":
    unittest.main()
