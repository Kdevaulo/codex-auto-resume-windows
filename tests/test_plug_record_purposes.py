"""P2's purposes and the moves of v0.6.14-beta.2: a record of the plug's goes only to a person's own conversation, a
continuation of the edition's own only while its turn is still the latest, a queued message a person edited is theirs,
and one a person cancelled - or any, while recovery is paused - is taken back out of Codex's queue, never sent twice.

The plug is test_plug_records' own (`Records`); the engine runs against codexsim, as every engine scenario does.
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from test_engine import T1, archive  # noqa: E402
from test_plug_records import KEY, WORDS, RecordCase, Records, record  # noqa: E402
from codex_auto_resume import continuation  # noqa: E402
from codex_auto_resume.domain import ids, plughands  # noqa: E402

CONTINUE = "The last turn ended without a reply. Please continue from where you stopped."


def latest_ordinal(h, thread=T1):
    return max(turn["rollout_ordinal"] for turn in h.home.turns(thread))


class PurposeTests(RecordCase):
    def continuation(self, h=None, **changes):
        h = h or self.h
        return record(**dict({"words": CONTINUE, "purpose": "continuation", "ordinal": latest_ordinal(h)}, **changes))

    def test_a_continuation_goes_while_its_turn_is_the_latest(self):
        plug = self.plug(self.continuation())
        self.h.tick()
        self.assertEqual(self.h.backend.send_calls, [(T1, CONTINUE + "\n\n" + ids.short_marker(KEY))])
        self.assertEqual(plug.moves, [("sent", None, None)])

    def test_a_continuation_after_a_later_turn_is_superseded_and_never_sent(self):
        handed = self.continuation()
        self.h.home.add_turn(T1)                    # somebody went on in the conversation
        plug = self.plug(handed)
        self.h.tick()
        self.assertEqual(self.h.backend.send_calls, [])
        self.assertEqual(plug.moves, [("superseded", "identity", "latest_turn_changed")])

    def test_nothing_goes_to_a_conversation_that_is_not_a_persons_own(self):
        """Fails with the gate reverted: an archived conversation - as a subagent's - reads as no one's."""
        archive(self.h.home, T1)
        for handed in (record(), self.continuation()):
            with self.subTest(purpose=handed.get("purpose", "message")):
                plug = self.plug(handed)
                self.h.tick()
                self.assertEqual(self.h.backend.send_calls, [])
                self.assertEqual(plug.moves[-1], ("waiting", "identity", "not_user_conversation"))

    def test_product_words_go_as_a_continuation_and_never_as_a_persons_message(self):
        product = continuation.build("usage_limit")
        with self.assertRaises(continuation.PromptError):
            continuation.validate_prompt(product)
        self.assertEqual(continuation.validate_continuation(product.replace("{", "").replace("}", "")),
                         product.replace("{", "").replace("}", ""))
        plug = self.plug(record(words=product))
        self.h.tick()
        self.assertEqual(self.h.backend.send_calls, [], "a person's message is never product text")
        self.assertEqual(plug.moves, [])

    def test_a_continuation_is_two_thousand_characters_at_most_and_fills_in_nothing(self):
        for words in ("x" * 2001, "Carry on with {reason}.", "  ", "Go on " + ids.MARKER_PREFIX):
            with self.subTest(words=words[:20]):
                with self.assertRaises(continuation.PromptError):
                    continuation.validate_continuation(words)
        plug = self.plug(self.continuation(words="x" * 2001))
        self.h.tick()
        self.assertEqual(self.h.backend.send_calls, [])

    def test_what_core_takes_of_a_record_says_its_purpose(self):
        base = record()
        self.assertEqual(plughands.records_of([base])[0]["purpose"], "message", "one naming none is a message")
        for bad in (dict(base, purpose="poem"), dict(base, purpose="continuation"),   # no ordinal
                    dict(base, ordinal=3), dict(base, purpose="continuation", ordinal=-1),
                    dict(base, queue_id="nope"), dict(base, withdraw=True)):
            with self.subTest(bad):
                self.assertEqual(plughands.records_of([bad]), ())


class InFlightTests(RecordCase):
    def sent(self, plug=None, **changes):
        """The record sent, and Codex holding it in its queue: what P2 hands over of it then."""
        self.h.backend.after_accept = "queue"
        plug = plug or self.plug()
        self.h.tick()
        self.assertEqual(plug.moves[-1][0], "sent")
        queue_id = self.h.home.queued(T1)[0]
        plug.handed = [record(state="in_flight", words=None, sent_at=self.h.now, queue_id=queue_id, **changes)]
        return plug, queue_id

    def test_the_queue_item_codex_took_it_as_is_told_with_the_send(self):
        plug = self.plug()
        self.h.backend.after_accept = "queue"
        self.h.tick()
        told = [(str(args[1]), args[0].get("queue_id")) for hook, args in plug.asked if hook == "moved"]
        self.assertEqual(told, [("sent", self.h.home.queued(T1)[0])])

    def test_a_queued_message_a_person_edited_is_handed_over_never_unproven(self):
        plug, queue_id = self.sent()
        self.h.home.edit_queued(queue_id, "my own words now")
        self.h.tick(advance=86400 * 2)
        self.assertEqual(plug.moves[-1][0], "handed_over")
        self.assertNotIn("unproven", [move for move, _g, _r in plug.moves])
        self.assertEqual(self.h.home.queued(T1), [queue_id], "never deleted")

    def test_a_cancel_takes_it_back_out_of_codexs_queue(self):
        plug, queue_id = self.sent(withdraw=True)
        self.h.tick(advance=5)
        self.assertEqual(plug.moves[-1], ("withdrawn", "consent", "user_cancelled"))
        self.assertEqual(self.h.home.queued(T1), [])
        self.assertEqual(len(self.h.backend.send_calls), 1, "never sent twice")

    def test_a_pause_takes_it_back_too(self):
        plug, queue_id = self.sent()
        self.h.tick(advance=5)                      # watched once in flight
        self.assertEqual(self.h.home.queued(T1), [queue_id])
        asked = len(plug.asked)
        self.h.store.set_enabled(False, self.h.now)
        self.h.tick(advance=5)
        # The plug is asked nothing while paused (K5): what core watched in flight is taken back all the same, and
        # the plug is told (P14), as core's own records are taken back by a Pause (H4).
        self.assertEqual([name for name, _args in plug.asked[asked:]], ["moved"])
        self.assertIn(("withdrawn", "consent", "paused"), plug.moves)
        self.assertEqual(self.h.home.queued(T1), [])

    def test_a_pause_right_after_the_send_takes_it_back_before_it_was_ever_watched(self):
        """Fails with the record remembered only once watched: paused at the very next tick, nothing would know it."""
        plug, queue_id = self.sent()
        self.h.store.set_enabled(False, self.h.now)
        self.h.tick(advance=5)
        self.assertIn(("withdrawn", "consent", "paused"), plug.moves)
        self.assertEqual(self.h.home.queued(T1), [])

    def test_one_codex_will_not_give_back_is_left_there_said_and_never_sent_again(self):
        plug, queue_id = self.sent(withdraw=True)
        self.h.backend.delete_result = False
        self.h.tick(advance=5)
        self.assertEqual(plug.moves[-1], ("withdraw_refused", "consent", "withdraw_unconfirmed"))
        deletes = len(self.h.backend.deleted)
        self.h.tick(advance=5)
        self.assertEqual(len(self.h.backend.deleted), deletes, "asked once, not every tick")
        self.assertEqual(len(self.h.backend.send_calls), 1)
        self.assertEqual(self.h.home.queued(T1), [queue_id])


if __name__ == "__main__":
    unittest.main()
