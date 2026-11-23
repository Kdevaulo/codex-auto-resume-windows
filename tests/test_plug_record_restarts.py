"""A record of the plug's that left Codex's queue with no marker ends within a bound, however often the watcher starts
(v0.6.26, review K3 of the third round's fixes).

B1's fix counted the day before such a record is unproven from when it was last seen in Codex's queue - or, for one a
restarted watcher never saw there, from that watcher's start. On a PC whose watcher starts at least once a day (shut
down each night) that day began again at every start: the record stayed in flight for good, and its conversation's later
records of the plug could not be claimed. Now a watcher that never saw it queued gives it an hour from its start
(recordchannel.RESTART_GRACE) for its marker to reach the history; one it finds still queued is watched as before.

The plug is test_plug_records' own (`Records`); the engine runs against codexsim, as every engine scenario does.
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from test_engine import T1  # noqa: E402
import test_plug_record_queue_held as held  # noqa: E402
from test_plug_records import RecordCase  # noqa: E402

DAY = 86400
HOUR = 3600


class RestartsTests(RecordCase):
    sent = held.QueueHeldTests.sent

    def restarts(self, plug, every, days):
        """A new watcher every `every` seconds for `days` days, ticking each minute for its first hour, then hourly:
        the hours after each send it was given ended, as a move."""
        ended, start = [], self.h.now
        while self.h.now - start < days * DAY and not ended:
            self.plugged(plug)
            began = self.h.now
            while self.h.now - began < every and not ended:
                self.h.tick(advance=60 if self.h.now - began < HOUR else HOUR)
                ended = [move for move in plug.moves if move[0] == "unproven"]
        return ended, (self.h.now - start) / HOUR

    def test_gone_from_the_queue_it_is_unproven_though_the_watcher_starts_every_twenty_hours(self):
        """Fails with each start counting a whole day again: ten days on it is still in flight."""
        plug, queue_id = self.sent()
        self.h.tick(advance=2 * DAY)
        self.assertTrue(self.h.home.remove_queued(queue_id))            # gone, nothing of it in the history
        ended, hours = self.restarts(plug, 20 * HOUR, 10)
        self.assertEqual(ended, [("unproven", None, None)])
        self.assertLessEqual(hours, 20 + 2, "by the first start after it left, an hour on")
        self.assertEqual(len(self.h.backend.send_calls), 1, "never sent again")

    def test_still_queued_it_is_never_unproven_across_the_daily_starts(self):
        plug, queue_id = self.sent()
        ended, _hours = self.restarts(plug, 20 * HOUR, 6)
        self.assertEqual(ended, [])
        self.assertEqual(self.h.home.queued(T1), [queue_id])
        self.assertEqual(len(self.h.backend.send_calls), 1)

    def test_delivered_after_a_start_it_is_delivered_not_unproven(self):
        plug, _queue_id = self.sent()
        self.h.tick(advance=DAY)
        self.h.home.dispatch(T1)                                         # Codex let the queue go meanwhile
        self.plugged(plug)
        self.h.tick(advance=60)
        self.assertEqual([move[0] for move in plug.moves], ["delivered"])


if __name__ == "__main__":
    unittest.main()
