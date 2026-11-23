"""matrix5 M1: a reading the meter saves in the same tick, after usage_pause's P8 tick marked what it read, is held before
the stop's turn after the reset is asked to start.

`after_reset` asked holding(), whose marks only `UsagePause._mark` writes, at P8's tick - before the meter's errand saved
that tick's reading. So at the first look after the five-hour reset, with the reading made then showing the weekly window
at 98 %, the stop's continuation started into the weekly window; the weekly was marked held only at the next tick. Now the
stop's errand marks first.

The meter's errand is stood in for by saving the reading right after usage_pause's own P8 tick, inside the same tick.

    CODEX_AR_EDITION=advanced PYTHONPATH="src;advanced/src;advanced/tests;tests" python -m unittest test_advanced_usagestop_mark_first
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from codex_auto_resume_advanced.engine.usagestop import UsageStop  # noqa: E402
from test_advanced_usagestop_carry_other_window import FIVE, OtherWindowCase  # noqa: E402
from test_advanced_usagestop_carry import DAY  # noqa: E402


class MarkFirst(OtherWindowCase):
    def test_a_window_over_in_the_reading_of_the_resets_tick_holds_the_start(self):
        """Fails with holding() asked before the mark: the continuation starts at the first look after the reset."""
        plug = self.stopped_at(FIVE, 98, 50, 3 * DAY)
        weekly_reset = self.weekly_reset
        self.h.now = self.reset + 120                                  # past the reset; the meter not read since
        real, read = UsageStop.tick, []

        def tick(code, view):
            answer = real(code, view)
            if not read:                                               # the meter's errand, later in this same tick
                read.append(True)
                self.meter(plug, 1, self.reset + 5 * 3600, 98, weekly_reset)
            return answer
        with patch.object(UsageStop, "tick", tick):
            self.h.tick(advance=1)
        self.assertEqual(self.starts, [], "no turn into the weekly window the same tick's reading shows over")
        self.assertTrue(self.code(plug).holding())
        for _ in range(3):
            self.h.tick(advance=60)
        self.assertEqual(self.starts, [])


if __name__ == "__main__":
    unittest.main()
