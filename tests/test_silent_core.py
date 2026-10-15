"""P15's SILENT (v0.6.16-beta.4): a continuation with no words at all, which core carries out only through a route that
takes words - calling it with none, under the client id it derives, and proving the turn by that id - and ignores
everywhere else: through `codex queue` the words go with their marker, as ever.

The plug is a test's own (test_plug_points.Asked); the route is test_route_unheld's, which runs the turn in codexsim.
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from test_engine import T1  # noqa: E402
from test_plug_points import Asked  # noqa: E402
from test_route_unheld import Headless, UnheldCase  # noqa: E402
from codex_auto_resume.domain import ids  # noqa: E402
from codex_auto_resume.domain.plug import ALTERNATIVES, DEFER, Alternative, Point  # noqa: E402


class Silent(Headless):
    """The route, its turn started under the client id it was handed - as our own app server starts one."""

    def resume(self, thread_id, *, launch_guard=None, still_unloaded=None, words=None, client_id=None):
        with launch_guard if launch_guard is not None else _nothing() as permitted:
            pass
        self.calls.append({"words": words, "client_id": client_id, "permitted": permitted})
        self.h.home.enqueue(thread_id, words or "", client_id=client_id)
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
        self.assertEqual(row["recovery_client_id"], derived, "written before the claim: its proof")
        self.assertEqual(row["state"], "queued", row["last_error"])
        self.h.tick(advance=2)
        self.assertEqual(self.h.record()["state"], "turn_started", "proven by the id, with no marker anywhere")

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

    def test_it_is_one_of_p15s_answers_and_null_never_gives_it(self):
        self.assertEqual(ALTERNATIVES[Point.DELIVERY], {Alternative.CLIENT_ID, Alternative.SILENT})
        from codex_auto_resume.domain.plug import NULL
        self.assertIs(NULL.delivery({}), DEFER)


if __name__ == "__main__":
    unittest.main()
