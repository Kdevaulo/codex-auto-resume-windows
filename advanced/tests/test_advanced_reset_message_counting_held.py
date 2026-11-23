"""matrix5 M3: a reset message still counting toward its reset never expires while the forced stop holds its conversation.

reset_message expires a message eight days after it was written (KEEP_FOR). audit4 B3 kept a message the stop holds
from expiring, but only a READY one: a message written six days before a weekly stop, counting for the weekly reset the
stop waits for, expired two days into the hold and was never carried. Now any pending message of a conversation whose
stop's turn waits is held from expiry, in either state.

    CODEX_AR_EDITION=advanced PYTHONPATH="src;advanced/src;advanced/tests;tests" python -m unittest test_advanced_reset_message_counting_held
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_advanced_usagestop_reset_message as instead  # noqa: E402
from test_advanced_usagestop_carry import WORDS  # noqa: E402
from test_advanced_usagestop_carry_other_window import WEEK, OtherWindowCase  # noqa: E402
from test_advanced_usagestop_carry import DAY  # noqa: E402
from test_engine import T1  # noqa: E402


class CountingHeld(OtherWindowCase):
    def test_a_counting_message_written_six_days_ago_outlives_the_hold(self):
        """Fails with only a READY message held: the eight days run out two days into the weekly hold."""
        plug = self.stopped_at(WEEK, 50, 98, 3 * DAY)
        state = plug.runtime.state
        rule = state.add_reset_rule("reset_message", "codex", WEEK, 1, thread_id=T1, words=WORDS,
                                    record_id=instead.RECORD, at=self.h.now - 6 * DAY)
        for _ in range(5):                                             # two and a half days of the weekly hold
            self.h.tick(advance=DAY / 2)
            self.meter(plug, 1, int(self.h.now) + 5 * 3600, 98, self.weekly_reset)
        row = state.reset_rule(rule)
        self.assertEqual(row["words"], WORDS, "kept with its words")
        self.assertNotIn(row["state"], ("done", "cancelled"))
        self.assertNotIn("resetmsg.expired", self.journal(plug))


if __name__ == "__main__":
    unittest.main()
