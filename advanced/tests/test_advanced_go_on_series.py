"""Go on for a recurring message held a period or more sends it once (v0.6.26, review V4 of the third round's fixes).

R1's fix made Go on send the held occurrence at once, at its old slot. For a series held longer than one period - a
daily message taken back by a Pause three days ago - that slot's next lay in the past too, so the tick's catch-up made
the latest occurrence and sent it as well: the same words twice within the hour. Now Go on takes such a series up as
the catch-up does: the occurrences that fell while it was held are used as missed, and the latest goes, once. A series
held less than a period keeps its slot (test_advanced_go_on_window).

Held against core's own engine, store and simulated Codex home (takingcase.py), as test_advanced_prompt_queue is.

    CODEX_AR_EDITION=advanced PYTHONPATH="src;advanced/src;advanced/tests;tests" python -m unittest test_advanced_go_on_series
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_advanced_go_on_window as window  # noqa: E402
from test_advanced_prompt_queue import QueueCase  # noqa: E402
from codex_auto_resume_advanced.vocabulary import PromptReason, PromptState  # noqa: E402

DAY = 86400


class GoOnSeriesTests(QueueCase):
    # The window module's harness, not its tests.
    go_on, held_at_a_pause = window.GoOnWindowTests.go_on, window.GoOnWindowTests.held_at_a_pause

    def series(self, every, occurrences):
        plug, prompt = self.held_at_a_pause(trigger="recurring", at=self.h.now + 5, every=every,
                                            occurrences=occurrences)
        return plug, prompt, plug.runtime.state.prompt(prompt)["due_at"]

    def ticks(self, count=240, step=30):
        for _ in range(count):
            self.h.tick(advance=step)

    def test_a_daily_series_held_three_days_sends_once_on_go_on(self):
        """Fails with Go on keeping the old slot: the held occurrence goes, then the catch-up sends the latest too."""
        plug, prompt, slot = self.series("day", 10)
        self.h.tick(advance=3 * DAY)
        before = len(self.sends())
        self.go_on(plug, prompt)
        self.ticks()
        self.assertEqual(len(self.sends()) - before, 1, "one send after Go on")
        row = plug.runtime.state.prompt(prompt)
        self.assertEqual((row["state"], row["sent_count"]), (PromptState.WAITING, 4),
                         "three that fell while held used as missed, the latest sent")
        self.assertEqual(row["due_at"], slot + 4 * DAY, "the next slot of the series, ahead")
        self.assertGreater(row["due_at"], self.h.now)

    def test_a_weekly_series_held_more_than_a_week_sends_once_on_go_on(self):
        plug, prompt, slot = self.series("week", 5)
        self.h.tick(advance=9 * DAY)
        before = len(self.sends())
        self.go_on(plug, prompt)
        self.ticks()
        self.assertEqual(len(self.sends()) - before, 1)
        row = plug.runtime.state.prompt(prompt)
        self.assertEqual((row["sent_count"], row["due_at"]), (2, slot + 14 * DAY))

    def test_a_series_with_none_left_after_its_missed_ones_ends_missed(self):
        plug, prompt, _slot = self.series("day", 2)
        self.h.tick(advance=3 * DAY)
        before = len(self.sends())
        self.go_on(plug, prompt)
        self.ticks(count=20)
        self.assertEqual(len(self.sends()) - before, 0)
        row = plug.runtime.state.prompt(prompt)
        self.assertEqual((row["state"], row["reason"], row["words"]), (PromptState.DONE, PromptReason.MISSED, None))


if __name__ == "__main__":
    unittest.main()
