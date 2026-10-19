"""P15's SILENT (v0.6.16-beta.4): a continuation with no words at all, which core carries out only through a route that
takes words - calling it with none, under the client id it derives, and proving the turn by that id - and ignores
everywhere else: through `codex queue` the words go with their marker, as ever.

And (v0.6.17) what it never silences: words that are not core's own template. Where the continuation carries another
capability's words (P4) or the person's words for this time, a turn with no words would throw them away - and the
person's would be spent as they went, lost for good - so P15 is not asked at all and the words go with the marker.

The plug is a test's own (test_plug_points.Asked); the route is test_route_unheld's, which runs the turn in codexsim.
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from codexsim import BASE  # noqa: E402
from test_engine import T1  # noqa: E402
from test_plug_points import Asked  # noqa: E402
from test_route_unheld import Headless, UnheldCase  # noqa: E402
from codex_auto_resume import machine, oncewords  # noqa: E402
from codex_auto_resume.domain import ids  # noqa: E402
from codex_auto_resume.domain.plug import ALTERNATIVES, DEFER, Alternative, Point  # noqa: E402


class Silent(Headless):
    """The route, its turn started under the client id it was handed - as our own app server starts one."""

    def resume(self, thread_id, *, launch_guard=None, still_unloaded=None, words=None, client_id=None):
        with launch_guard if launch_guard is not None else _nothing() as permitted:
            pass
        self.calls.append({"words": words, "client_id": client_id, "permitted": permitted})
        if not words:
            # As Codex does (M3B, 2026-10-16): a turn with no words has no message of anyone's, and no client id.
            turn = self.h.home.add_turn(thread_id, None, "inProgress", user_text=None, progress=False)
        else:
            self.h.home.enqueue(thread_id, words, client_id=client_id)
            turn = self.h.home.dispatch(thread_id, status="inProgress")
        return {"outcome": "ran", "turn_id": turn}


class _nothing:
    def __enter__(self):
        return True

    def __exit__(self, *_):
        return False


class SilentTests(UnheldCase):
    def test_a_route_that_takes_words_is_handed_none_and_the_turn_is_proven_by_its_id(self):
        """Fails with SILENT reverted: the route would be handed the words and the marker."""
        route = Silent(self.h)
        self.armed(route, delivery=Alternative.SILENT)
        self.closed()
        self.h.tick()
        (call,) = route.calls
        row = self.h.record()
        derived = ids.continuation_client_id(row["interruption_id"])
        self.assertEqual((call["words"], call["client_id"]), ("", derived))
        self.assertEqual(row["recovery_client_id"], derived, "written before the claim")
        self.assertEqual(row["state"], "turn_started", "proven at once by the turn id the route returned (M3B)")
        self.assertEqual(row["recovery_turn_id"], self.h.home.turns(T1)[-1]["turn_id"])
        self.h.tick(advance=2)
        self.assertEqual(self.h.record()["state"], "turn_started", "and the watch agrees, with no marker anywhere")

    def test_without_it_the_route_is_handed_the_words_and_the_marker(self):
        route = Silent(self.h)
        self.armed(route)
        self.closed()
        self.h.tick()
        (call,) = route.calls
        row = self.h.record()
        self.assertTrue(call["words"].endswith("\n\n" + row["marker"]), call["words"])
        self.assertIsNone(row["recovery_client_id"])

    def test_through_codex_queue_it_is_ignored_and_the_marker_goes(self):
        self.plugged(Asked(delivery=Alternative.SILENT))
        self.ready_after_reset(self.h)
        self.h.tick()
        (sent,) = self.h.backend.send_calls
        row = self.h.record(T1)
        self.assertIn(row["marker"], sent[1])
        self.assertIsNone(row["recovery_client_id"])

    def test_the_plain_continuation_with_no_other_words_is_silent_as_before(self):
        """The template alone is core's own: nothing of anyone else's is thrown away, so SILENT stands."""
        route = Silent(self.h)
        self.armed(route, delivery=Alternative.SILENT)
        self.closed()
        self.h.tick()
        (call,) = route.calls
        self.assertEqual(call["words"], "")
        self.assertEqual(self.h.record()["recovery_client_id"],
                         ids.continuation_client_id(self.h.record()["interruption_id"]))

    def test_it_is_one_of_p15s_answers_and_null_never_gives_it(self):
        self.assertEqual(ALTERNATIVES[Point.DELIVERY], {Alternative.CLIENT_ID, Alternative.SILENT})
        from codex_auto_resume.domain.plug import NULL
        self.assertIs(NULL.delivery({}), DEFER)


WORDS = "Then run the tests, please."


class YieldsToOtherWordsTests(UnheldCase):
    """v0.6.17: what SILENT never silences. A turn with no words carries nothing of anyone's, so where the
    continuation holds words that are not core's own template, P15 is not asked and the words go with the marker."""

    def words_file(self, h=None):
        """The real side file the person's words for this time are kept in, on the engine `armed` just built."""
        h = h or self.h
        if h.engine.once_words is None:
            h.engine.once_words = oncewords.OnceWords(h.root / oncewords.FILE_NAME)
        return h.engine.once_words

    def test_another_capabilitys_words_are_sent_and_silent_yields(self):
        """Fails with the yield reverted: the route is handed "", and the words P4 gave are gone."""
        route = Silent(self.h)
        self.armed(route, delivery=Alternative.SILENT, text="Please go on with the {category} task.")
        self.closed()
        self.h.tick()
        (call,) = route.calls
        row = self.h.record()
        self.assertEqual(call["words"], "Please go on with the usage_limit task.\n\n" + row["marker"])
        self.assertIsNone(row["recovery_client_id"], "it goes by its marker, as one P15 never answered")
        self.assertEqual(row["state"], "queued")

    def test_the_persons_words_for_this_time_are_neither_thrown_away_nor_spent_unsent(self):
        """Fails with the yield reverted: the route is handed "", and the words are removed from the file
        all the same - the person's message for this time lost, neither sent nor kept."""
        route = Silent(self.h)
        self.armed(route, delivery=Alternative.SILENT)
        self.closed()
        key = self.h.record()["interruption_id"]
        self.words_file().put(key, WORDS, now=BASE)
        self.h.tick()
        (call,) = route.calls
        row = self.h.record()
        self.assertIn("\n\n" + WORDS + "\n\n", call["words"])
        self.assertTrue(call["words"].endswith("\n\n" + row["marker"]), call["words"])
        self.assertIsNone(row["recovery_client_id"])
        self.assertIsNone(self.words_file().words(key), "spent, because they went with this continuation")

    def test_words_waiting_are_never_both_unsent_and_spent(self):
        """The invariant P-10 broke, whichever way P15 is answered and whatever the route answers: words a route
        never started with are still there for the next continuation; words it may have sent went with it, and
        are spent as a send's are. Fails with either fix reverted: silent with ran or unknown (the route handed
        ""), and the put-back with not_started (the words spent off the file by a route that never started)."""
        for outcome in ("ran", "not_started", "unknown"):
            for silent in (True, False):
                with self.subTest(outcome=outcome, silent=silent):
                    h = self.fresh()
                    route = Headless(h, outcome)
                    self.armed(route, h, **({"delivery": Alternative.SILENT} if silent else {}))
                    self.closed(h)
                    key = h.record()["interruption_id"]
                    self.words_file(h).put(key, WORDS, now=BASE)
                    h.tick()
                    (call,) = route.calls
                    kept = self.words_file(h).words(key)
                    if outcome == "not_started":
                        self.assertEqual(kept, WORDS, "never handed to Codex: kept for the next continuation")
                        self.assertIn(h.record()["state"], machine.WAITING, "and the record waits for it")
                    else:
                        self.assertIn("\n\n" + WORDS + "\n\n", call["words"] or "", "handed with the continuation")
                        self.assertIsNone(kept, "spent with it, as a send's are")

    def test_the_standard_edition_is_asked_nothing_and_its_words_go_as_before(self):
        """The standard edition's plug is NULL: it names no route and answers no P15, so none of this runs for it.
        With the app closed the record waits for the app with its words kept, and nobody is asked who holds the
        conversation; once the app holds it, the words go through `codex queue` before the marker, as ever. It
        holds by design with or without the v0.6.17 changes: the standard edition is not one of them."""
        app = self.h.backend.app
        self.plugged(None)
        self.assertTrue(self.h.engine.plug.null)
        self.closed()
        key = self.h.record()["interruption_id"]
        self.words_file().put(key, WORDS, now=BASE)
        self.h.tick()
        self.assertEqual(self.h.backend.send_calls, [])
        self.assertEqual(self.h.record()["state"], "waiting_for_app")
        self.assertEqual(self.h.backend.holder_calls, [], "no route, so no one is asked who holds it")
        self.assertEqual(self.words_file().words(key), WORDS)
        self.h.backend.app = app
        self.h.backend.loaded_map[T1] = "loaded"
        self.h.tick(advance=self.h.options["state_poll_seconds"] + 1)      # its next look, waiting for the app
        (sent,) = self.h.backend.send_calls
        row = self.h.record()
        self.assertIn("\n\n" + WORDS + "\n\n" + row["marker"], sent[1])
        self.assertIsNone(row["recovery_client_id"])
        self.assertIsNone(self.words_file().words(key), "spent with the send that carried them")


if __name__ == "__main__":
    unittest.main()
