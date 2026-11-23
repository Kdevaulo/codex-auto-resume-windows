"""v0.6.26 third round A1 and A3: a reset seen under a full weekly window is held a window's length past that weekly
reset, and wake_for_reset is told the next look of what window_anchor holds open.

A1: the hold ended ten minutes past the weekly reset, so a PC asleep through those minutes ended the occasion unread at
its first tick after waking (skip_weekly, ANCHOR_RESET_DONE stamped) - and an idle window teaches no new reset, so "Start
right after a reset" stopped for good. A3: the hold lives in the watcher's memory only, and wake_for_reset asked the stamps
of what is done alone, so nothing woke the PC for that weekly reset.

The clock is the test's and every usage read a fake session it counts (test_advanced_window_anchor.AnchorCase).

    CODEX_AR_EDITION=advanced PYTHONPATH="src;advanced/src;advanced/tests" python -m unittest test_advanced_window_anchor_weekly_sleep
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from codex_auto_resume_advanced.engine import anchor  # noqa: E402
from codex_auto_resume_advanced.engine.wake import WakeForReset  # noqa: E402
from codex_auto_resume_advanced.vocabulary import OptionKey  # noqa: E402
from test_advanced_window_anchor_retry import EVERY, RetryCase  # noqa: E402

HOUR = 3600
DAY = anchor.DAY


class UnderAFullWeeklyWindow(RetryCase):
    """test_advanced_window_anchor_weekly_looks' helpers, without its tests (a subclass of that class would run them twice)."""

    def full(self, days=2):
        """The weekly window full, its reset `days` off, as the world reads it from now on."""
        self.world.week = 100.0
        self.weekly_reset = int(self.now) + days * DAY
        reply = self.world.reply

        def answered():
            found = reply()
            found["rateLimitsByLimitId"]["codex"]["secondary"]["resetsAt"] = self.weekly_reset
            return found
        self.world.reply = answered

    def reads(self):
        return sum(1 for call in self.world.calls if call != "account/read")

    def step_to(self, until, step=EVERY / 2):
        while self.now + step <= until:
            self.look(step)


class AsleepThroughTheWeeklyReset(UnderAFullWeeklyWindow):
    def test_a_pc_that_wakes_an_hour_after_the_weekly_reset_still_starts_the_window(self):
        """Fails with the old ten minutes: the first look an hour on ends the occasion as skip_weekly, nothing started."""
        self.reset()
        self.full(days=2)
        self.look()
        self.now = float(self.weekly_reset + HOUR)                # asleep from before the reset until an hour past it
        self.world.week = 3.0
        self.look()
        self.run_through()
        self.assertEqual(len(self.world.started), 1)
        self.assertNotIn("anchor.skip_weekly", self.codes())
        self.assertEqual(self.done(), (None, self.seen), "the reset seen is the one handled")

    def test_the_first_look_is_still_five_minutes_past_the_weekly_reset(self):
        """A guard: holding longer adds no look before the weekly reset (passes with the fix reverted)."""
        self.reset()
        self.full(days=2)
        self.look()
        self.step_to(self.weekly_reset + anchor.RETRY_EVERY - anchor.LOOK_EVERY)
        self.assertEqual(self.reads(), 1)

    def test_still_full_after_its_reset_it_ends_in_one_line(self):
        """Past the weekly reset with the window still full and no reset ahead, it ends at once, as before."""
        self.reset()
        self.full(days=1)
        self.look()
        self.step_to(self.weekly_reset + 3 * anchor.RETRY_EVERY, step=anchor.RETRY_EVERY)
        self.assertEqual(self.codes(), ["anchor.skip_weekly"])


class TheWakeIsToldTheNextLook(UnderAFullWeeklyWindow):
    def next_look(self):
        return self.stamped(OptionKey.ANCHOR_NEXT_LOOK)

    def test_the_next_look_of_a_weekly_hold_is_stamped(self):
        """Fails without the stamp: nothing outside the watcher's memory knows of the look past the weekly reset."""
        self.reset()
        self.full(days=2)
        self.look()
        self.assertEqual(self.next_look(), self.weekly_reset + anchor.RETRY_EVERY)

    def test_the_stamp_goes_once_nothing_is_held(self):
        self.reset()
        self.full(days=2)
        self.look()
        self.now = float(self.weekly_reset + anchor.RETRY_EVERY)
        self.world.week = 3.0
        self.look()
        self.run_through()
        self.assertIsNone(self.next_look())

    def test_wake_for_reset_wakes_for_it(self):
        """Fails with `_anchor_due` asking next_due alone: the reset seen is past, so it answers nothing."""
        self.reset()
        self.full(days=2)
        self.look()
        due = self.weekly_reset + anchor.RETRY_EVERY
        self.assertEqual(WakeForReset._anchor_due(_Wake(self.rt, self.now), self.now), due)


class _Scoped:
    """What wake_for_reset's `_anchor_due` reads of the state: window_anchor's arming, its options and its stamps."""

    def __init__(self, rt, now):
        self.rt, self._now = rt, now

    def armed(self, capability):
        return True                                       # on in every test here (AnchorCase.on)

    def options_of(self, capability):
        return self.rt.state.options(capability)

    def stamped_of(self, capability, key):
        return self.rt.state.stamped(capability, key)


class _Wake:
    def __init__(self, rt, now):
        self._scoped = _Scoped(rt, now)


if __name__ == "__main__":
    unittest.main()
