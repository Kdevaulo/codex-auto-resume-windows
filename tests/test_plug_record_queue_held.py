"""A record of the plug's that Codex holds in its queue (v0.6.26, finding B1 of the third audit): a queue Codex paused -
usage_pause stopped the turn, or the person pressed Stop and has not resumed - keeps it there for days. Its fate is
known, so it is never told unproven while Codex is seen holding it with its marker - which would turn its capability
off and end every other queued message - and never sent again; it is delivered once Codex lets it go. One that leaves
the queue with no marker in the history is unproven a day after it was last seen there, and one whose fate was never
known is unproven a day after it was sent, as before.

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
from test_plug_records import RecordCase, record  # noqa: E402

DAY = 86400
HOUR = 3600


class QueueHeldTests(RecordCase):
    def sent(self, h=None):
        """A record sent and held in Codex's queue, as P2 hands it in flight then: (plug, queue id)."""
        h = h or self.h
        h.backend.after_accept = "queue"
        plug = self.plug(record(), h=h)
        h.tick()
        self.assertEqual(plug.moves[-1][0], "sent")
        queue_id = h.home.queued(T1)[0]
        plug.handed = [record(state="in_flight", words=None, sent_at=h.now, queue_id=queue_id)]
        plug.moves.clear()
        return plug, queue_id

    def test_held_in_codexs_queue_for_days_it_is_never_unproven_nor_sent_again(self):
        """Fails with the unproven clock running while the queue row shows it there: unproven on the 25th hour."""
        plug, queue_id = self.sent()
        for _ in range(24 * 9):
            self.h.tick(advance=HOUR)
        moves = [move for move, _gate, _reason in plug.moves]
        self.assertNotIn("unproven", moves)
        self.assertEqual(moves, [], "nothing ended it: Codex still holds it")
        self.assertEqual(self.h.home.queued(T1), [queue_id], "still in Codex's queue, never deleted")
        self.assertEqual(self.h.backend.deleted, [])
        self.assertEqual(len(self.h.backend.send_calls), 1, "never sent twice")

    def test_once_codex_lets_the_queue_go_it_is_delivered(self):
        plug, _queue_id = self.sent()
        self.h.tick(advance=3 * DAY)
        self.h.home.dispatch(T1)
        self.h.tick(advance=5)
        self.assertEqual(plug.moves, [("delivered", None, None)])
        self.assertEqual(len(self.h.backend.send_calls), 1)

    def test_edited_in_the_queue_after_days_it_is_handed_over(self):
        plug, queue_id = self.sent()
        self.h.tick(advance=2 * DAY)
        self.h.home.edit_queued(queue_id, "the person's own words now")
        self.h.tick(advance=5)
        self.assertEqual(plug.moves, [("handed_over", None, None)])

    def test_gone_from_the_queue_with_no_marker_it_is_unproven_a_day_after_it_was_last_seen_there(self):
        plug, queue_id = self.sent()
        self.h.tick(advance=2 * DAY)                           # seen there, two days after it was sent
        self.assertTrue(self.h.home.remove_queued(queue_id))  # gone, and nothing of it in the history
        self.h.tick(advance=60)
        self.assertEqual(plug.moves, [], "between the queue and the history: not unproven at once")
        self.h.tick(advance=DAY - 120)
        self.assertEqual(plug.moves, [])
        self.h.tick(advance=120)
        self.assertEqual(plug.moves, [("unproven", None, None)])
        self.assertEqual(len(self.h.backend.send_calls), 1, "never sent again")

    def test_after_a_restart_one_codex_took_counts_its_day_from_the_watchers_start(self):
        """Nothing of what this process saw survives a restart: one gone from the queue since may have sat there until
        then, so its day counts from the new watcher's start - never from its send, days before."""
        plug, queue_id = self.sent()
        self.h.tick(advance=3 * DAY)
        self.h.home.remove_queued(queue_id)
        self.h.now += 60
        self.plugged(plug)                                     # a new watcher: nothing of what the first one saw
        self.h.tick()
        self.assertEqual(plug.moves, [])
        self.h.tick(advance=DAY - 120)
        self.assertEqual(plug.moves, [])
        self.h.tick(advance=120)
        self.assertEqual(plug.moves, [("unproven", None, None)])

    def test_with_no_queue_id_known_it_is_found_in_the_queue_by_its_proof(self):
        """The chat keeps no queue id, and a restart forgets the one Codex gave: one Codex still holds is found by its
        proof and never unproven while there - and, its id unknown, never taken back by a guess. Fails without the
        look by proof: unproven a day after its send while Codex still holds it."""
        plug, queue_id = self.sent()
        plug.handed = [record(state="in_flight", words=None, sent_at=self.h.now)]      # no queue id
        self.plugged(plug)                                                             # a restarted watcher
        for _ in range(24 * 3):
            self.h.tick(advance=HOUR)
        self.assertEqual(plug.moves, [])
        self.assertEqual(self.h.home.queued(T1), [queue_id])
        self.h.home.remove_queued(queue_id)
        self.h.tick(advance=DAY - 60)
        self.assertEqual(plug.moves, [], "a day from when it was last seen there")
        self.h.tick(advance=HOUR)
        self.assertEqual(plug.moves, [("unproven", None, None)])
        self.assertEqual(len(self.h.backend.send_calls), 1)

    def test_one_whose_fate_was_never_known_is_still_unproven_a_day_after_it_was_sent(self):
        plug = self.plug(record(state="in_flight", words=None, sent_at=self.h.now - DAY + 30))
        self.h.tick()
        self.assertEqual(plug.moves, [])
        self.h.tick(advance=60)
        self.assertEqual(plug.moves, [("unproven", None, None)])
        self.assertEqual(self.h.backend.send_calls, [])

    def test_a_cancel_still_takes_it_back_out_of_the_queue(self):
        plug, queue_id = self.sent()
        self.h.tick(advance=2 * DAY)
        plug.handed = [record(state="in_flight", words=None, sent_at=self.h.now - 2 * DAY, queue_id=queue_id,
                              withdraw=True)]
        self.h.tick(advance=5)
        self.assertEqual(plug.moves, [("withdrawn", "consent", "user_cancelled")])
        self.assertEqual(self.h.home.queued(T1), [])


if __name__ == "__main__":
    unittest.main()
