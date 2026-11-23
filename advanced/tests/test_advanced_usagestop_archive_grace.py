"""review6 A3: a held message in a conversation archived at the reset waits the day core's own route would give it.

review4 V2 ended such a message at the first look after the reset (resetmsg.not_started, its words deleted), so an archive
undone two minutes later had already lost the person's words, where core's route for the same message waits a day
(DUE_FOR) for a conversation it does not find. Now the stop's turn waits that day: back within it, the message is carried;
only after it does the message end, as one that waited too long ("not sent: it waited too long" on the page).

    CODEX_AR_EDITION=advanced PYTHONPATH="src;advanced/src;advanced/tests;tests" python -m unittest test_advanced_usagestop_archive_grace
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_advanced_usagestop_carry_other_window import FIVE, OtherWindowCase  # noqa: E402
from test_advanced_usagestop_carry import DAY, WORDS  # noqa: E402
from test_engine import T1, archive  # noqa: E402

HOUR = 3600


def unarchive(home, thread_id):
    with home._db("state_5.sqlite") as db:
        db.execute("UPDATE threads SET archived=0 WHERE id=?", (thread_id,))


class ArchiveGrace(OtherWindowCase):
    def archived_at_the_reset(self):
        plug = self.stopped_at(FIVE, 98, 50, 3 * DAY)
        rule = self.message(plug, FIVE, self.reset + 60)
        archive(self.h.home, T1)
        self.h.now = self.reset + 120
        self.meter(plug, 1, self.reset + 5 * HOUR, 50, self.weekly_reset)
        self.h.tick(advance=60)
        return plug, rule

    def test_an_archive_undone_within_the_day_keeps_the_message_and_the_stop_carries_it(self):
        """Fails with review4 V2's end at the first look: the words gone, the catalog's continuation sent instead."""
        plug, rule = self.archived_at_the_reset()
        row = plug.runtime.state.reset_rule(rule)
        self.assertEqual((row["state"], row["words"]), ("ready", WORDS), "kept through the first look")
        self.assertIn("not_continued", self.kinds(plug), "told it is continued once it is open")
        self.h.tick(advance=120)
        unarchive(self.h.home, T1)
        for _ in range(3):
            self.h.tick(advance=60)
        self.assertEqual(self.starts, self.carried(), "the stop's turn carries the message")
        self.assertEqual(self.rule_row(plug, rule), ("done", "delivered"))
        self.assertNotIn("pause.continued", self.journal(plug))

    def test_archived_for_a_day_it_ends_as_one_that_waited_too_long(self):
        plug, rule = self.archived_at_the_reset()
        self.h.tick(advance=DAY / 2)
        self.assertEqual(plug.runtime.state.reset_rule(rule)["state"], "ready", "half a day: still waiting")
        for _ in range(3):
            self.h.tick(advance=DAY / 4)
        row = plug.runtime.state.reset_rule(rule)
        self.assertEqual((row["state"], row["reason"], row["words"]), ("done", "expired", None))
        self.assertIn("resetmsg.expired", self.journal(plug))
        self.assertEqual(self.starts, [])
        self.assertEqual(self.h.backend.send_calls, [])


if __name__ == "__main__":
    unittest.main()
