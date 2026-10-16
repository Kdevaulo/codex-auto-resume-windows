"""P16 with the Codex app closed, and a route that carries core's words (v0.6.16-beta.4).

Until now core asked P16 only where the app ran and said a conversation was notLoaded; with no app, a record waited
`desktop_app_unavailable` (A11). From this version, where the plug wants P16 at all, core asks once more: with the app
closed and nothing holding the conversation's writer lock (`Backend.holder`, one Restart Manager look), P16 is asked
with `holder="none", app=False`, and only a route is taken. A route may say it takes words (`takes_words`): core then
builds the continuation before the claim exactly as for a send - its template or the Custom message, the marker at its
end - and hands them over with the client id it derived. A route that answers "ran" leaves the record queued, proven
by its marker like any delivered send; the re-check under the dispatch lock and the route's own last look ask the same
two things again.

The plug is a test's own (test_plug_points.Asked); the engine runs against codexsim.
"""
from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
import sys
import unittest

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from codexsim import new_id  # noqa: E402
from test_engine import T1  # noqa: E402
from test_plug_points import Asked, PluggedCase  # noqa: E402
from codex_auto_resume import machine  # noqa: E402
from codex_auto_resume.domain import ids  # noqa: E402
from codex_auto_resume.domain.plug import DEFER, Alternative, Point  # noqa: E402
from codex_auto_resume.domain.plughands import Route  # noqa: E402


class Headless:
    """A route that runs one turn itself: it records what it was handed and, with `ran`, starts the turn in the
    simulated Codex home with the words it was given - as our own app server would."""
    takes_words = True

    def __init__(self, h, outcome="ran", *, during=None):
        self.h, self.outcome, self.during = h, outcome, during
        self.calls = []

    def resume(self, thread_id, *, launch_guard=None, still_unloaded=None, words=None, client_id=None):
        with launch_guard if launch_guard is not None else nullcontext(True) as permitted:
            pass
        if self.during is not None:
            self.during()
        unheld = still_unloaded() if still_unloaded is not None else None
        self.calls.append({"thread": thread_id, "words": words, "client_id": client_id, "permitted": permitted,
                           "unheld": unheld,
                           "state": self.h.store.get(self.h.record()["interruption_id"])["state"]})
        if not unheld:
            return {"outcome": "not_started", "error_code": "queue_preflight_failed"}
        if self.outcome == "raise":
            raise OSError("the route exploded")
        if self.outcome == "ran":
            self.h.home.enqueue(thread_id, words, client_id=new_id())
            turn = self.h.home.dispatch(thread_id, status="inProgress")
            return {"outcome": "ran", "turn_id": turn}
        return {"outcome": self.outcome}


class Wordless(Headless):
    takes_words = False

    def resume(self, thread_id, *, launch_guard=None, still_unloaded=None):
        self.calls.append({"thread": thread_id})
        return {"outcome": "accepted"}


def holding(backend):
    """codexsim's backend, which is v0.6.10's file and asks no one who holds a conversation, given Backend.holder:
    `holder_map` says who holds each, "unknown" for the rest, and `holder_calls` keeps every ask."""
    backend.holder_map, backend.holder_calls = {}, []

    def holder(thread_id):
        backend.holder_calls.append(thread_id)
        return backend.holder_map.get(thread_id, "unknown")
    backend.holder = holder
    return backend


class UnheldCase(PluggedCase):
    def fresh(self, **kwargs):
        made = super().fresh(**kwargs)
        holding(made.backend)
        return made

    def closed(self, h=None, holder="none"):
        """A usage-limited conversation past its reset, with the Codex app closed and `holder` on its lock."""
        h = h or self.h
        self.ready_after_reset(h, loaded=False)
        h.backend.app = None
        h.backend.holder_map[T1] = holder

    def armed(self, route, h=None, **answers):
        h = h or self.h
        plug = Asked(unloaded=lambda record: route if record.get("app") is False else DEFER,
                     wants=lambda point: point == Point.UNLOADED, **answers)
        self.plugged(plug, h)
        return plug


class AskedTests(UnheldCase):
    def test_closed_and_unheld_the_plug_is_asked_with_no_app(self):
        route = Headless(self.h)
        plug = self.armed(route)
        self.closed()
        self.h.tick()
        asked = [arguments[0] for hook, arguments in plug.asked if hook == "unloaded"]
        self.assertEqual(len(asked), 1)
        self.assertEqual((asked[0]["holder"], asked[0]["app"]), ("none", False))
        self.assertEqual(len(route.calls), 1)

    def test_null_never_asks_who_holds_it(self):
        """Fails with the `wants` check reverted: the standard edition would ask the Restart Manager."""
        self.closed()
        self.plugged(Asked())
        self.h.tick()
        self.assertEqual(self.h.backend.holder_calls, [])
        self.assertEqual(self.h.record()["last_error"], "desktop_app_unavailable")

    def test_a_held_or_unknown_lock_waits_as_before(self):
        for holder in ("session", "unknown"):
            with self.subTest(holder):
                h = self.fresh()
                route = Headless(h)
                self.armed(route, h)
                self.closed(h, holder=holder)
                h.tick()
                self.assertEqual(route.calls, [])
                self.assertEqual(h.record()["last_error"], "desktop_app_unavailable")

    def test_only_a_route_is_taken_with_no_app(self):
        self.closed()
        self.plugged(Asked(unloaded=Alternative.QUEUE_FOR_OPEN, wants=True))
        self.h.tick()
        self.assert_no_send()
        self.assertEqual(self.h.record()["last_error"], "desktop_app_unavailable")

    def test_with_the_app_running_it_is_asked_as_app_free(self):
        plug = Asked(unloaded=DEFER, wants=True)
        self.plugged(plug)
        self.ready_after_reset(loaded=False)
        self.h.backend.loaded_map[T1] = "notLoaded"
        self.h.tick()
        asked = [arguments[0] for hook, arguments in plug.asked if hook == "unloaded"]
        self.assertEqual((asked[0]["holder"], asked[0]["app"]), ("app_free", True))


class WordsTests(UnheldCase):
    def test_the_words_are_cores_with_the_marker_decided_before_the_claim(self):
        route = Headless(self.h)
        self.armed(route)
        self.closed()
        self.h.tick()
        (call,) = route.calls
        row = self.h.record()
        self.assertTrue(call["words"].endswith("\n\n" + row["marker"]), call["words"])
        self.assertEqual(call["client_id"], ids.continuation_client_id(row["interruption_id"]))
        self.assertEqual(call["state"], "submitting", "called after the claim")
        self.assertIs(call["permitted"], True)

    def test_a_route_that_takes_no_words_is_called_as_before(self):
        route = Wordless(self.h)
        self.armed(route)
        self.closed()
        self.h.tick()
        self.assertEqual(route.calls, [{"thread": T1}])
        self.assertIsInstance(Route(route.resume), Route)

    def test_ran_is_queued_and_then_delivered_by_its_marker(self):
        route = Headless(self.h)
        self.armed(route)
        self.closed()
        self.h.tick()
        row = self.h.record()
        self.assertEqual(row["state"], "queued", row["last_error"])
        self.assertIsNone(row["queue_id"])
        self.assertEqual(machine.decode_gates(row["gate_eval"])["thread_available"], (machine.PASS, machine.PLUGGED))
        self.h.tick(advance=2)
        self.assertEqual(self.h.record()["state"], "turn_started")

    def test_a_raising_route_is_an_uncertain_submission_never_tried_again(self):
        route = Headless(self.h, "raise")
        self.armed(route)
        self.closed()
        self.h.tick()
        self.assertEqual(self.h.record()["state"], "submission_unknown")
        self.h.tick(advance=3600)
        self.assertEqual(len(route.calls), 1)

    def test_the_app_starting_between_claim_and_route_is_not_started(self):
        """The route's last look (still_unloaded) sees the app: nothing ran, the claim is given back."""
        h = self.h

        def app_opens():
            h.backend.app = {"pid": 1, "created": 1}
        route = Headless(h, during=app_opens)
        self.armed(route)
        self.closed()
        h.tick()
        self.assertIs(route.calls[0]["unheld"], False)
        row = h.record()
        self.assertIn(row["state"], machine.WAITING, row["state"])
        self.assertEqual(row["chain_continuations"], 0, "its claim given back")

    def test_its_own_server_holding_the_lock_at_the_last_look_still_runs(self):
        """A route's own app server holds the writer lock from its thread/resume on (Backend.holder: "ours"): the last
        look takes it as no other holder. Fails with the look reverted to "none" alone: no turn could ever start."""
        h = self.h

        def resumed_on_our_server():
            h.backend.holder_map[T1] = "ours"
        route = Headless(h, during=resumed_on_our_server)
        self.armed(route)
        self.closed()
        h.tick()
        self.assertIs(route.calls[0]["unheld"], True)
        self.assertEqual(h.record()["state"], "queued")

    def test_another_holder_at_the_last_look_still_stops_it(self):
        h = self.h

        def a_terminal_takes_it():
            h.backend.holder_map[T1] = "session"
        route = Headless(h, during=a_terminal_takes_it)
        self.armed(route)
        self.closed()
        h.tick()
        self.assertIs(route.calls[0]["unheld"], False)
        self.assertIn(h.record()["state"], machine.WAITING)

    def test_our_own_server_is_never_a_reason_to_ask_p16(self):
        route = Headless(self.h)
        self.armed(route)
        self.closed(holder="ours")
        self.h.tick()
        self.assertEqual(route.calls, [])
        self.assertEqual(self.h.record()["last_error"], "desktop_app_unavailable")

    def test_a_holder_appearing_before_the_claim_stops_it(self):
        h = self.h
        route = Headless(h)
        plug = self.armed(route)
        self.closed()
        holders = iter(["none", "session"])
        h.backend.holder = lambda thread_id: next(holders, "session")
        h.tick()
        self.assertEqual(route.calls, [])
        self.assertIn(h.record()["state"], machine.WAITING)
        del plug


if __name__ == "__main__":
    unittest.main()
