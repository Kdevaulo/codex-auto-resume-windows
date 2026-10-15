"""Proactive usage near a limit (v0.6.16-beta.3, issue #29): the usage meter, and the wrap-up and the pause that
require it.

The meter reads usage on its own while the Codex app runs, at the spacing a person chose, keeps the windows and warns
once a window; it never satisfies core's usage gate. The pause holds core's records and the edition's own
continuations while a window is over the person's percentage, until it resets, and never a person's own message.
The wrap-up sends one message of the edition's own words to each conversation switched on with a turn running, once
for a window - through core's own queue route, into the turn it was made for. Each is off until a person turns it on.

    PYTHONPATH=src python -m unittest discover -s advanced/tests
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))

import advancedcase as ac  # noqa: E402
from takingcase import TakingCase  # noqa: E402
from codex_auto_resume.domain.plug import DEFER, Alternative, Point, Surface  # noqa: E402
from codex_auto_resume_advanced import registry, statement, surfaces  # noqa: E402
from codex_auto_resume_advanced.engine import usage  # noqa: E402
from codex_auto_resume_advanced.registry import USAGE_METER, USAGE_PAUSE, USAGE_WRAP_UP, Registry  # noqa: E402
from codex_auto_resume_advanced.vocabulary import Actor, ArmingState, ContinuationKind, OptionKey, OffReason  # noqa: E402
from test_engine import T1  # noqa: E402

ENGINE = ac.ENGINE


def reply(five=40.0, week=20.0, *, five_reset=None, week_reset=None):
    """An account/rateLimits/read answer as Codex gives one: a five-hour and a weekly window."""
    now = int(ac.NOW)
    return {"rateLimitsByLimitId": {"codex": {
        "primary": {"usedPercent": five, "windowDurationMins": 300, "resetsAt": five_reset or now + 3600},
        "secondary": {"usedPercent": week, "windowDurationMins": 10080, "resetsAt": week_reset or now + 86400}}}}


class Session:
    def __init__(self, answer, calls):
        self.answer, self.calls = answer, calls

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        return False

    def call(self, method, params=None):
        self.calls.append(method)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def _view_all():
    return {"status": "ok", "engine": {"found": True, "version": ENGINE},
            "capabilities": {name: {"state": "COMPATIBLE", "reason": "local_checks_passed"}
                             for name in ("usage_probe", "exact_thread_recovery")}}


class UsageCase(ac.AdvancedCase):
    def setUp(self):
        super().setUp()
        self.compat = _view_all()
        self.rt = self.runtime(USAGE_METER, USAGE_WRAP_UP, USAGE_PAUSE)
        self.rt.arming.catalogs = statement.CATALOGS
        self.answer, self.calls, self.app = reply(), [], True
        code = self.rt._code_of(USAGE_METER)
        code._session = lambda: Session(self.answer, self.calls)
        code._app_running = lambda: self.app

    def on(self, *capabilities):
        for capability in capabilities:
            definition = self.rt.registry.get(capability)
            also = [{"capability": other, "revision": self.rt.registry.get(other).revision,
                     "warnings": [str(w) for w in self.rt.arming.warnings(self.rt.registry.get(other))],
                     "engine_version": ENGINE}
                    for other in self.rt.registry.requires(capability)
                    if self.rt.arming.current().get(other) != ArmingState.ARMED]
            result = self.rt.arming.arm(capability, state="armed", revision=definition.revision,
                                        generation=self.rt.state.meta()["generation"], acknowledged_version=ENGINE,
                                        warnings=[str(w) for w in self.rt.arming.warnings(definition)],
                                        also=also or None, actor=Actor.DASHBOARD)
            self.assertTrue(result["done"], result)
        self.rt.states(fresh=True)

    def look(self):
        """One tick, its errand run - what core does with the answer at P8."""
        answer = self.rt.tick(None)
        if answer is not DEFER:
            answer.run(lambda: None)
        self.rt.states(fresh=True)


class DefinitionTests(unittest.TestCase):
    def test_the_three_depart_require_and_offer_what_the_design_says(self):
        self.assertEqual((USAGE_METER.departs_from, USAGE_METER.points, USAGE_METER.requires),
                         (("C4", "C9"), frozenset({Point.TICK}), ()))
        self.assertEqual((USAGE_WRAP_UP.departs_from, USAGE_WRAP_UP.requires), (("A13", "A26"), ("usage_meter",)))
        self.assertEqual((USAGE_PAUSE.departs_from, USAGE_PAUSE.requires), (("C9",), ("usage_meter",)))
        self.assertEqual({option.key: option.default for option in USAGE_METER.options},
                         {OptionKey.POLL_MINUTES: 15, OptionKey.WARN_FIVE_HOUR: 85, OptionKey.WARN_WEEKLY: 85})
        self.assertEqual({option.key: option.default for option in USAGE_WRAP_UP.options},
                         {OptionKey.WRAP_FIVE_HOUR: 90, OptionKey.WRAP_WEEKLY: 90, OptionKey.WRAP_STYLE: 2})
        self.assertEqual({option.key: option.default for option in USAGE_PAUSE.options},
                         {OptionKey.PAUSE_FIVE_HOUR: 95, OptionKey.PAUSE_WEEKLY: 95})
        self.assertEqual(USAGE_METER.option(OptionKey.POLL_MINUTES).choices, (5, 10, 15, 20, 30, 45, 60))
        for capability in ("usage_meter", "usage_wrap_up", "usage_pause"):
            self.assertIn(capability, registry.REGISTRY.ids)

    def test_each_wording_is_a_continuation_core_sends_in_every_language(self):
        from codex_auto_resume import continuation, l10n
        for key in usage.STYLE_KEYS.values():
            for locale in l10n.LOCALES:
                with self.subTest(key=key, locale=locale):
                    continuation.validate_continuation(statement.CATALOGS.text(key, locale))


class MeterTests(UsageCase):
    def test_off_it_reads_nothing_and_shows_nothing(self):
        self.look()
        self.assertEqual((self.calls, self.rt.state.meter()), ([], {}))
        self.assertEqual(surfaces.meter_view(self.rt), {})

    def test_on_it_reads_at_the_spacing_the_person_chose_and_only_while_the_app_runs(self):
        self.on("usage_meter")
        self.look()
        self.assertEqual(self.calls, ["account/rateLimits/read"])
        self.assertEqual({key: row["used_percent"] for key, row in self.rt.state.meter().items()},
                         {("codex", 300): 40.0, ("codex", 10080): 20.0})
        self.now += 14 * 60
        self.look()
        self.assertEqual(len(self.calls), 1, "not before fifteen minutes")
        self.now += 61
        self.look()
        self.assertEqual(len(self.calls), 2)
        self.app = False
        self.now += 16 * 60
        self.look()
        self.assertEqual(len(self.calls), 2, "never while the Codex app is not running")

    def test_a_reading_that_fails_is_counted_and_changes_nothing(self):
        self.on("usage_meter")
        self.look()
        before = self.rt.state.meter()
        self.answer = OSError("no")
        self.now += 16 * 60
        self.look()
        self.assertEqual(self.rt.state.meter(), before)

    def test_it_warns_once_for_a_window_and_again_after_it_resets(self):
        self.on("usage_meter")
        self.answer = reply(five=86)
        self.look()
        notices = surfaces.meter_view(self.rt)["meter"]["notices"]
        self.assertEqual([notice["window_minutes"] for notice in notices], [300])
        warned = self.rt.state.meter()[("codex", 300)]["warned_at"]
        self.now += 16 * 60
        self.look()
        self.assertEqual(self.rt.state.meter()[("codex", 300)]["warned_at"], warned, "once for that window")
        self.now += 16 * 60
        self.answer = reply(five=88, five_reset=int(self.now) + 18000)
        self.look()
        self.assertGreater(self.rt.state.meter()[("codex", 300)]["warned_at"], warned, "a new window warns again")

    def test_the_person_chooses_each_windows_percentage(self):
        self.on("usage_meter")
        self.rt.arming.set_option("usage_meter", "warn_weekly", 50, generation=self.rt.state.meta()["generation"],
                                  actor=Actor.DASHBOARD)
        self.answer = reply(five=60, week=55)
        self.look()
        windows = {w["window_minutes"]: w["band"] for w in surfaces.meter_view(self.rt)["meter"]["windows"]}
        self.assertEqual(windows, {300: "none", 10080: "warn"})

    def test_it_never_answers_where_core_decides_whether_a_recovery_may_go(self):
        """The meter answers at P8 alone: no gate, no schedule, nothing core's usage gate reads."""
        self.on("usage_meter")
        self.look()
        record = {"interruption_id": ac.KEY, "thread_id": ac.THREAD}
        for point, arguments in ((Point.GATES, ("usage", record, {})), (Point.SCHEDULE, (record, self.now))):
            self.assertIs(self.rt.ask(point, *arguments), DEFER)

    def test_turning_it_off_deletes_its_reading(self):
        self.on("usage_meter")
        self.look()
        self.assertTrue(self.rt.state.meter())
        self.rt.arming.disarm("usage_meter", actor=Actor.DASHBOARD)
        self.assertEqual(self.rt.state.meter(), {})

    def test_the_tray_and_the_status_carry_it_only_while_it_is_on(self):
        plug = ac.advanced.AdvancedPlug(self.paths, **self.options(USAGE_METER, USAGE_WRAP_UP, USAGE_PAUSE))
        self.addCleanup(lambda: plug._runtime and plug._runtime.state.close())
        plug._runtime = self.rt
        self.assertNotIn("meter", surfaces.answer(self.rt, Surface.TRAY, {}))
        self.on("usage_meter")
        self.look()
        for surface in (Surface.TRAY, Surface.STATUS):
            self.assertIn("meter", surfaces.answer(self.rt, surface, {}))


class RequirementTests(UsageCase):
    def test_the_wrap_up_and_the_pause_turn_the_meter_on_and_off_with_them(self):
        self.on("usage_pause")
        self.assertEqual(self.rt.arming.current()["usage_meter"], ArmingState.ARMED)
        result = self.rt.arming.disarm("usage_meter", actor=Actor.DASHBOARD)
        self.assertEqual(result["also_off"], ["usage_pause"])
        self.assertEqual(self.rt.state.arming()["usage_pause"]["reason"], OffReason.REQUIREMENT_OFF)


class PauseTests(UsageCase):
    CORE = {"interruption_id": ac.KEY, "thread_id": ac.THREAD}

    def test_over_the_percentage_it_holds_core_and_the_editions_own_continuations_until_the_reset(self):
        self.on("usage_pause")
        self.answer = reply(five=96)
        self.look()
        self.look()                                   # the pause's own tick marks the window
        code = self.rt._code_of(USAGE_PAUSE)
        self.assertIs(self.rt.ask(Point.GATES, "usage", self.CORE, {}), Alternative.HOLD)
        self.assertTrue(code.holds({"state": "waiting", "purpose": "continuation"}))
        for untouched in ({"state": "waiting", "purpose": "message"}, {"state": "waiting", "purpose": "wrap_up"},
                          {"state": "in_flight", "purpose": "continuation"}):
            self.assertFalse(code.holds(untouched), untouched)
        self.now = self.rt.state.meter()[("codex", 300)]["reset_at"] + 61
        self.assertIs(self.rt.ask(Point.GATES, "usage", self.CORE, {}), DEFER)

    def test_below_the_percentage_nothing_is_held(self):
        self.on("usage_pause")
        self.answer = reply(five=94)
        self.look()
        self.look()
        self.assertIs(self.rt.ask(Point.GATES, "usage", self.CORE, {}), DEFER)

    def test_off_nothing_is_held(self):
        self.on("usage_meter")
        self.answer = reply(five=99)
        self.look()
        self.look()
        self.assertIs(self.rt.ask(Point.GATES, "usage", self.CORE, {}), DEFER)


class WrapUpTests(TakingCase):
    """Through core's own engine and simulated Codex home: the wrap-up goes into the running turn, once."""
    DEFINITION = USAGE_WRAP_UP
    BESIDE = (USAGE_METER,)

    def setUp(self):
        super().setUp()
        self.compat = _view_all()

    def arm(self, plug, state="armed", capability=None, **changes):
        definition = plug.runtime.registry.get(capability or self.cap)
        changes.setdefault("warnings", [str(w) for w in plug.runtime.arming.warnings(definition)])
        return super().arm(plug, state=state, capability=capability, **changes)

    def running(self, percent=91):
        plug = self.armed()
        plug.runtime._code_of(plug.runtime.registry.get(self.cap))._home = self.h.home.root
        self.h.backend.loaded_map[T1] = "loaded"
        turn = self.h.home.add_turn(T1, status="inProgress", progress=False)
        plug.runtime.state.save_meter([{"bucket": "codex", "window_minutes": 300, "used_percent": percent,
                                        "reset_at": int(self.h.now) + 3600}], at=self.h.now)
        return plug, turn

    def test_a_conversation_with_a_turn_running_is_sent_one_wrap_up_for_the_window(self):
        plug, _turn = self.running()
        for _ in range(3):
            self.h.tick(advance=61)
        sent = [prompt for thread, prompt in self.h.backend.send_calls if thread == T1]
        self.assertEqual(len(sent), 1, self.h.logs[-10:])
        self.assertTrue(sent[0].startswith(statement.CATALOGS.text("continue.wrap_up.standard")))
        for _ in range(3):
            self.h.tick(advance=61)
        self.assertEqual(len([t for t, _p in self.h.backend.send_calls if t == T1]), 1, "once for the window")

    def test_below_the_percentage_nothing_is_sent(self):
        self.running(percent=80)
        for _ in range(3):
            self.h.tick(advance=61)
        self.assertEqual(self.h.backend.send_calls, [])

    def test_a_turn_that_ended_before_it_went_gets_none(self):
        """Made while the app does not hold the conversation, it waits; the turn then ends, and it is superseded -
        never sent into a turn it was not made for."""
        plug, _turn = self.running()
        self.h.backend.loaded_map[T1] = "notLoaded"
        self.h.tick(advance=61)
        rows = plug.runtime.state.continuations(capability=self.cap, pending=None)
        self.assertEqual(len(rows), 1)
        self.h.home.add_turn(T1)                      # a later turn: the running one is no longer the latest
        self.h.backend.loaded_map[T1] = "loaded"
        for _ in range(3):
            self.h.tick(advance=61)
        self.assertEqual(self.h.backend.send_calls, [])
        row = plug.runtime.state.continuations(capability=self.cap, pending=None)[0]
        self.assertEqual(row["reason"], "superseded")

    def test_a_conversation_codex_makes_for_itself_gets_none(self):
        """Only a conversation core would recover is asked: a subagent, a review, a memory pass and an agent-made
        conversation running beside the person's own get no wrap-up, which core would keep waiting for good."""
        plug, _turn = self.running()
        internal = []
        for kind in ("subagent", "guardian_review", "memory_consolidation", "agent_created_thread"):
            thread = str(uuid.uuid4())
            self.h.home.add_thread(thread, thread_source=kind)
            self.h.home.add_turn(thread, status="inProgress", progress=False)
            self.h.backend.loaded_map[thread] = "loaded"
            internal.append(thread)
        for _ in range(3):
            self.h.tick(advance=61)
        rows = plug.runtime.state.continuations(capability=self.cap, pending=None)
        self.assertEqual({row["thread_id"] for row in rows}, {T1})
        self.assertEqual([thread for thread, _p in self.h.backend.send_calls], [T1])

    def test_rows_core_would_never_send_end_and_crowd_out_none(self):
        """Ten left waiting where core would never send them - conversations it does not take up - end superseded at
        the next P2, and the person's own conversation is sent its wrap-up beside them."""
        plug, _turn = self.running()
        stale = []
        for index in range(10):
            thread = str(uuid.uuid4())
            self.h.home.add_thread(thread, thread_source="subagent")
            self.h.home.add_turn(thread, status="inProgress", progress=False)
            key = "%064x" % (9000 + index)
            self.assertTrue(plug.runtime.state.add_continuation(key, self.cap, ContinuationKind.WRAP_UP, thread,
                                                                statement.CATALOGS.text("continue.wrap_up.short"),
                                                                ordinal=0))
            stale.append(thread)
        for _ in range(4):
            self.h.tick(advance=61)
        self.assertEqual([thread for thread, _p in self.h.backend.send_calls], [T1])
        rows = {row["thread_id"]: row for row in plug.runtime.state.continuations(capability=self.cap, pending=None)}
        self.assertEqual({rows[thread]["reason"] for thread in stale}, {"superseded"})


if __name__ == "__main__":
    unittest.main()
