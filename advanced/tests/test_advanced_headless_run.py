"""Run a conversation here while Codex is closed (v0.6.16-beta.4): the shipped capability against core's own engine,
store and simulated Codex home (takingcase.py), its route's session a fake app server that runs the turn in that
home, as our own server would.
"""
from __future__ import annotations

from pathlib import Path
import sys
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from takingcase import TakingCase  # noqa: E402
from advancedcase import ENGINE  # noqa: E402
from codexsim import new_id  # noqa: E402
from codex_auto_resume import machine  # noqa: E402
from codex_auto_resume.domain.plug import DEFER, Point  # noqa: E402
from codex_auto_resume_advanced import registry  # noqa: E402
from codex_auto_resume_advanced.codex import headless  # noqa: E402
from codex_auto_resume_advanced.engine.headless import HeadlessRunCode  # noqa: E402
from codex_auto_resume_advanced.registry import HEADLESS_RUN  # noqa: E402
from codex_auto_resume_advanced.vocabulary import (ArmingState, ArmingWarning, JournalCode, Measurement,  # noqa: E402
                                                   OptionKey, RunEnd, Verdict)
from test_advanced_headless import SAVED, Server  # noqa: E402
from test_engine import T1  # noqa: E402
from test_route_unheld import holding  # noqa: E402


class HomeServer(Server):
    """The fake app server, its turn started in the harness's Codex home with the words it was given."""

    def __init__(self, capability, h, **options):
        super().__init__(capability, **options)
        self.h = h

    def call(self, method, params=None):
        answer = super().call(method, params)
        if method == "turn/start":
            words = params["input"][0]["text"] if params["input"] else ""
            self.h.home.enqueue(T1, words, client_id=params.get("clientUserMessageId") or new_id())
            turn = self.h.home.dispatch(T1, status="inProgress")
            answer = {"turn": {"id": turn}}
            self.replies["turn/start"], self.turn = answer, turn
        return answer

    def _complete(self, status):
        with self.lock:
            self.events.append({"method": "turn/completed", "params": {
                "threadId": T1, "turn": {"id": getattr(self, "turn", None), "status": status}}})


class HeadlessCase(TakingCase):
    DEFINITION = HEADLESS_RUN

    def fresh(self, **kwargs):
        made = super().fresh(**kwargs)
        holding(made.backend)
        return made

    def setUp(self):
        super().setUp()
        self.follower = headless.Follower(poll=0.01)
        self.servers = []
        self.app_running = False

    def arm(self, plug, state="armed", capability=None, **changes):
        definition = plug.runtime.registry.get(capability or self.cap)
        changes.setdefault("warnings", [str(word) for word in plug.runtime.arming.warnings(definition)])
        return super().arm(plug, state=state, capability=capability, **changes)

    def armed(self, h=None, state="armed", **server):
        plug = super().armed(h, state=state)
        code = plug.runtime._code_of(self.DEFINITION)
        h = h or self.h

        def opening(capability):
            self.servers.append(HomeServer(capability, h, **server))
            return self.servers[-1]
        code._open, code.follower, code._app = opening, self.follower, (lambda: self.app_running)
        return plug

    def closed(self, h=None, holder="none"):
        h = h or self.h
        self.ready_after_reset(h, loaded=False)
        h.backend.app = None
        h.backend.holder_map[T1] = holder

    def settle(self):
        deadline = time.monotonic() + 5
        while self.follower.live() is not None and time.monotonic() < deadline:
            time.sleep(0.01)


class RunTests(HeadlessCase):
    def test_off_it_waits_for_the_app_as_the_standard_edition_does(self):
        self.plugged(self.advanced())
        self.closed()
        self.h.tick()
        self.assert_no_send()
        self.assertEqual(self.h.record()["last_error"], "desktop_app_unavailable")
        self.assertEqual(self.servers, [])

    def test_watched_it_only_journals(self):
        plug = self.armed(state="shadow")
        self.closed()
        self.h.tick()
        self.assertEqual(self.servers, [])
        self.assertIn((JournalCode.WOULD_HAVE, Point.UNLOADED, Point.UNLOADED), self.journal(plug))

    def test_on_it_runs_the_one_turn_here_paid_for_and_proven_by_its_marker(self):
        plug = self.armed()
        self.closed()
        self.h.tick()
        row = self.h.record()
        self.assertEqual(row["state"], "queued", row["last_error"])
        self.assertEqual([spend[0] for spend in self.spends(plug)], [self.cap])
        (server,) = self.servers
        self.assertIn(row["marker"], dict(server.calls)["turn/start"]["input"][0]["text"])
        self.settle()
        self.h.tick(advance=2)
        self.assertEqual(self.h.record()["state"], "turn_started")
        self.assert_no_send()

    def test_only_with_no_holder_and_codex_closed(self):
        for holder in ("session", "unknown"):
            with self.subTest(holder):
                h = self.fresh()
                self.armed(h)
                self.closed(h, holder=holder)
                h.tick()
                self.assertEqual(self.servers, [])

    def test_one_run_at_a_time(self):
        code = HeadlessRunCode(None, follower=self.follower)
        code.bind(object())
        self.follower._run = {"stop": None, "shown": {"key": "k"}}
        record = {"interruption_id": "%064x" % 3, "app": False, "holder": "none", "category": "usage_limit"}
        self.assertIs(code.unloaded(record), DEFER)
        self.follower._run = None

    def test_never_for_a_conversation_the_running_app_or_another_session_holds(self):
        """Fails with the unheld check reverted: it would run a conversation the app or a session holds."""
        code = HeadlessRunCode(None, follower=self.follower)
        code.bind(object())
        for where in ({"app": True, "holder": "app_free"}, {"app": True, "holder": "session"}, {}):
            record = dict({"interruption_id": "%064x" % 3, "category": "usage_limit"}, **where)
            self.assertIs(code.unloaded(record), DEFER, where)

    def test_a_full_context_window_is_not_its_to_run(self):
        code = HeadlessRunCode(None, follower=self.follower)
        code.bind(object())
        record = {"interruption_id": "%064x" % 3, "app": False, "holder": "none", "category": "terminal_invalid"}
        self.assertIs(code.unloaded(record), DEFER)

    def test_the_hours_option_caps_the_turn(self):
        plug = self.armed(completes_after=None)
        self.choose(plug, OptionKey.CEILING_HOURS, 2)
        self.closed()
        self.h.tick()
        live = self.follower.live()
        self.assertAlmostEqual(live["ends_by"] - live["started_at"], 2 * 3600, delta=5)
        self.follower.stop()
        self.settle()

    def test_full_access_is_refused_before_anything_starts_and_it_waits_again(self):
        plug = self.armed(replies={"thread/resume": dict(SAVED, sandbox={"type": "dangerFullAccess"})})
        self.closed()
        self.h.tick()
        self.assertNotIn("turn/start", self.servers[0].methods())
        self.assertIn(self.h.record()["state"], machine.WAITING)
        self.assertTrue(self.servers[0].closed)


class StopTests(HeadlessCase):
    def test_a_stop_from_the_dashboard_interrupts_it_at_the_next_tick(self):
        from codex_auto_resume_advanced import surfaces
        plug = self.armed(completes_after=None)
        self.closed()
        self.h.tick()
        key = self.h.record()["interruption_id"]
        self.h.tick(advance=1)                          # the P8 tick writes the live run's row
        self.assertEqual([row["interruption_id"] for row in plug.runtime.state.runs()], [key])
        answered = surfaces.bridge(plug.runtime, "advanced-headless-stop", {"interruption_id": key})
        self.assertTrue(answered["done"], answered)
        self.h.tick(advance=1)
        self.settle()
        self.h.tick(advance=1)
        self.assertEqual(plug.runtime.state.runs(live=False)[0]["end"], RunEnd.INTERRUPTED)
        self.assertIn("turn/interrupt", self.servers[0].methods())

    def test_no_mcp_tool_reaches_stop(self):
        from codex_auto_resume_advanced import surfaces
        self.assertNotIn("advanced-headless-stop", [tool["name"] for tool in surfaces.TOOLS])


class RegistryTests(HeadlessCase):
    def test_it_answers_at_p16_after_queue_for_open_and_departs_from_what_the_design_says(self):
        definition = registry.HEADLESS_RUN
        self.assertEqual(definition.departs_from, ("0.5", "A2", "A11", "B3", "B4", "E8", "F8"))
        self.assertEqual((definition.compat, definition.measurements),
                         ("loaded_state_detection", (Measurement.M6, Measurement.M6B)))
        ids = [d.id for d in registry.DEFINITIONS]
        # v0.6.16-beta.4: after queue for opening, and after compact_continue, whose own record is its route's.
        self.assertEqual(ids.index("headless_run"), ids.index("queue_for_open") + 2)
        self.assertEqual(ids.index("compact_continue"), ids.index("queue_for_open") + 1)

    def test_unmeasured_on_this_codex_is_a_warning_never_a_refusal(self):
        plug = self.advanced()
        definition = plug.runtime.registry.get(self.cap)
        self.assertIn(ArmingWarning.UNMEASURED, plug.runtime.arming.warnings(definition))
        self.measured = {Measurement.M6: (Verdict.PASS, ENGINE), Measurement.M6B: (Verdict.PASS, ENGINE)}
        self.assertNotIn(ArmingWarning.UNMEASURED, plug.runtime.arming.warnings(definition))
        self.measured = {}
        self.arm(plug)
        self.assertEqual(plug.runtime.states(fresh=True)[self.cap], ArmingState.ARMED)


if __name__ == "__main__":
    unittest.main()
