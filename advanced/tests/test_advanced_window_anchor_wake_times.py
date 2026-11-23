"""audit4 B2: wake_for_reset is told only an occasion's own time by window_anchor - never a five-minute retry.

A3's fix stamped ANCHOR_NEXT_LOOK for every occasion held open, so each RETRY_EVERY retry of a passing failure (a read
that fails: signed out, no network on waking, Codex restarting) and each look of a ceiling's hold became a wake time:
sixty wakes in five hours, a day of them for a ceiling. Now only the look past a full weekly window's reset is stamped
(test_advanced_window_anchor_weekly_sleep), and for a ceiling's hold the minute the ceiling frees.

    CODEX_AR_EDITION=advanced PYTHONPATH="src;advanced/src;advanced/tests" python -m unittest test_advanced_window_anchor_wake_times
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from codex_auto_resume_advanced.engine import anchor  # noqa: E402
from codex_auto_resume_advanced.engine.wake import WakeForReset  # noqa: E402
from codex_auto_resume_advanced.registry import WINDOW_ANCHOR  # noqa: E402
from codex_auto_resume_advanced.vocabulary import OptionKey  # noqa: E402
from test_advanced_window_anchor import CAP  # noqa: E402
from test_advanced_window_anchor_retry import EVERY, RetryCase  # noqa: E402
from test_advanced_window_anchor_weekly_sleep import _Wake  # noqa: E402


class WakeTimes(RetryCase):
    def wake_for(self):
        return WakeForReset._anchor_due(_Wake(self.rt, self.now), self.now)

    def test_a_failing_read_is_retried_without_a_wake_time(self):
        """Fails with every held look stamped: each five-minute retry is a time to wake the PC for."""
        self.reset()
        self.world.broken = True
        seen = set()
        for _retry in range(12):
            self.look(EVERY + 1)
            seen.add(self.wake_for())
            self.assertIsNone(self.stamped(OptionKey.ANCHOR_NEXT_LOOK))
        self.assertEqual(seen, {None}, "no wake for an hour of retries")

    def test_a_ceiling_hold_is_woken_for_once_when_the_ceiling_frees(self):
        """Fails with every held look stamped (a time five minutes on, moving each look) or with none."""
        self.reset()
        made = self.now - 3600
        for _start in range(WINDOW_ANCHOR.ceilings.per_day):
            self.assertTrue(self.rt.state.counted(CAP, "started", at=made))
        self.look()
        first = self.stamped(OptionKey.ANCHOR_NEXT_LOOK)
        self.assertIsNotNone(first)
        self.assertTrue(made + anchor.DAY <= first <= made + anchor.DAY + 60, (first, made + anchor.DAY))
        for _retry in range(6):
            self.look(EVERY + 1)
            self.assertEqual(self.stamped(OptionKey.ANCHOR_NEXT_LOOK), first, "the same time at every look")
        self.assertEqual(self.wake_for(), first)


if __name__ == "__main__":
    unittest.main()
