"""review4 V2 (the coordinator's call, after audit4 B3 and the owner's answer of 2026-11-23): what ends the forced stop's
hold on a person's reset message, so the message is never held for ever.

- Resume pressed before the reset: newer work in the conversation ends the stop's hold at once - not at the stop
  window's reset, days later - and the message goes by reset_message's own route at its own reset, its day counted
  from the Resume. Before, the hold lasted to the stop window's reset (69 hours after the Resume in the review's run).
- The conversation archived or gone: the stop's turn can never start there, and the message stayed READY with its
  words for good, nothing said. Now it ends as a message not started (resetmsg.not_started), its words gone, and the
  person is told (the near-limit `not_continued` notice).

    CODEX_AR_EDITION=advanced PYTHONPATH="src;advanced/src;advanced/tests;tests" python -m unittest test_advanced_usagestop_hold_ends
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_advanced_usagestop_carry_other_window import FIVE, WEEK, OtherWindowCase  # noqa: E402
from test_advanced_usagestop_carry import DAY  # noqa: E402
from test_engine import T1, archive  # noqa: E402

HOUR = 3600


class ResumeBeforeTheReset(OtherWindowCase):
    def test_the_persons_resume_ends_the_hold_and_the_message_goes_by_its_own_route(self):
        """Fails with the hold lasting to the weekly reset: two hours after the Resume the message still waits."""
        plug = self.stopped_at(WEEK, 50, 98, 3 * DAY)
        weekly_reset = self.weekly_reset
        self.h.now = self.reset + 120                                  # the five-hour window reset; the weekly holds
        self.meter(plug, 1, self.reset + 5 * 3600, 98, weekly_reset)
        rule = self.message(plug, FIVE, self.reset + 60)
        for _ in range(3):
            self.h.tick(advance=60)
        self.nothing_sent_yet(plug, rule)
        self.h.tick(advance=2 * HOUR)
        self.h.home.add_turn(T1, status="completed", user_text="the person's own turn after Resume")
        for _ in range(3):
            self.h.tick(advance=60)
        self.assertEqual(self.outcome(plug), "superseded", "the Resume ended the stop's hold")
        self.assertEqual(len(self.h.backend.send_calls), 1, "the message goes by reset_message's own route")
        self.assertEqual(self.starts, [], "no turn of the stop's")
        self.assertNotIn("resetmsg.expired", self.journal(plug))


class ArchivedWhileHeld(OtherWindowCase):
    def test_a_message_in_an_archived_conversation_ends_and_the_person_is_told(self):
        """Fails with the message held for ever: READY with its words twelve days on, nothing said."""
        plug = self.stopped_at(FIVE, 98, 50, 3 * DAY)
        rule = self.message(plug, FIVE, self.reset + 60)
        archive(self.h.home, T1)
        self.h.now = self.reset + 120
        self.meter(plug, 1, self.reset + 5 * 3600, 50, self.weekly_reset)
        for _ in range(3):
            self.h.tick(advance=60)
        row = plug.runtime.state.reset_rule(rule)
        self.assertEqual((row["state"], row["reason"], row["words"]), ("done", "not_started", None))
        self.assertIn("resetmsg.not_started", self.journal(plug))
        self.assertIn("not_continued", self.kinds(plug))
        self.assertEqual(self.starts, [])
        self.assertEqual(self.h.backend.send_calls, [])


if __name__ == "__main__":
    unittest.main()
