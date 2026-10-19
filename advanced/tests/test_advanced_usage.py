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
from codex_auto_resume_advanced.engine import usage, wrapwords  # noqa: E402
from codex_auto_resume_advanced.registry import USAGE_METER, USAGE_PAUSE, USAGE_WRAP_UP, Registry  # noqa: E402
from codex_auto_resume_advanced.vocabulary import (Actor, ArmingState, ContinuationKind, OptionKey, OffReason,  # noqa: E402
                                                   Refusal, SpendOutcome)
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
        self.assertEqual((USAGE_PAUSE.departs_from, USAGE_PAUSE.requires), (("A2", "B3", "C9", "H6"), ("usage_meter",)))
        self.assertEqual({option.key: option.default for option in USAGE_METER.options},
                         {OptionKey.POLL_MINUTES: 15, OptionKey.WARN_FIVE_HOUR: 85, OptionKey.WARN_WEEKLY: 85,
                          OptionKey.WINDOW_FIVE_HOUR: 1, OptionKey.WINDOW_WEEKLY: 1})
        self.assertEqual({option.key: option.default for option in USAGE_WRAP_UP.options},
                         {OptionKey.WRAP_FIVE_HOUR: 90, OptionKey.WRAP_WEEKLY: 90, OptionKey.WRAP_STYLE: 2,
                          OptionKey.STOP_WORDS_FIVE_HOUR: 95, OptionKey.STOP_WORDS_WEEKLY: 95,
                          OptionKey.WRAP_RESET_TIME: 1, OptionKey.WRAP_AFTER_RESET: 1,
                          OptionKey.WINDOW_FIVE_HOUR: 1, OptionKey.WINDOW_WEEKLY: 1})
        self.assertEqual({option.key: option.default for option in USAGE_PAUSE.options},
                         {OptionKey.PAUSE_FIVE_HOUR: 97, OptionKey.PAUSE_WEEKLY: 97,
                          OptionKey.WINDOW_FIVE_HOUR: 1, OptionKey.WINDOW_WEEKLY: 1})
        self.assertEqual(USAGE_METER.option(OptionKey.POLL_MINUTES).choices, (5, 10, 15, 20, 30, 45, 60))
        for capability in ("usage_meter", "usage_wrap_up", "usage_pause"):
            self.assertIn(capability, registry.REGISTRY.ids)

    def test_the_statements_name_what_the_three_now_do(self):
        """v0.6.16-beta.4: each statement says what its capability does now, in every language's own words for it - the
        meter's windows switched off on their own and its spacing typed in, the wrap-up's wordings, Include the reset
        time and Continue after the reset, the forced stop by its new name - and was given a new revision for it."""
        from codex_auto_resume import l10n
        self.assertEqual((USAGE_METER.revision, USAGE_WRAP_UP.revision, USAGE_PAUSE.revision), (2, 2, 2))
        for locale in l10n.LOCALES:
            with self.subTest(locale=locale):
                words = statement.CATALOGS.own(locale)
                wrap = words["statement.usage_wrap_up.does"]
                for label in ("page.option.wrap_reset_time", "page.option.wrap_after_reset"):
                    self.assertIn(words[label].rstrip("."), wrap, label)
                self.assertIn(words["name.usage_pause"], words["statement.usage_meter.stop"])
                self.assertIn("60", words["statement.usage_meter.does"])

    def test_each_wording_is_a_continuation_core_sends_in_every_language(self):
        """Each of the four wordings, for each window, filled in: words core sends as a continuation, in every
        language - and the one with the numbers names the window and both percentages (v0.6.16-beta.4)."""
        from codex_auto_resume import l10n
        for style in usage.STYLES:
            for minutes in usage.WINDOWS:
                for locale in l10n.LOCALES:
                    with self.subTest(style=style, minutes=minutes, locale=locale):
                        words = wrapwords.render(style=style, minutes=minutes, used=91.6, stop_at=96, locale=locale)
                        self.assertIsNotNone(words)
                        weekly = wrapwords.render(style=style, minutes=minutes, used=91.6, stop_at=96, locale=locale,
                                                  reset_at=1_800_000_000, include_reset=True)
                        self.assertIsNotNone(weekly)
                        self.assertIn(wrapwords.reset_words(1_800_000_000, minutes, locale), weekly)
                        if style == 4:
                            self.assertIn("91", words)
                            self.assertIn("96", words)
                            self.assertIn(wrapwords.window_words(minutes, locale), words)


class CustomNumberTests(UsageCase):
    """v0.6.16-beta.4 (f): every number has Custom... beside its presets - any whole percentage, a spacing of 5 to 60."""

    def set(self, capability, key, value):
        return self.rt.arming.set_option(capability, key, value, generation=self.rt.state.meta()["generation"],
                                         actor=Actor.DASHBOARD)

    def test_a_number_typed_in_is_taken_in_its_range_and_refused_outside_it(self):
        for capability, key, good, bad in (("usage_wrap_up", OptionKey.WRAP_FIVE_HOUR, 93, (0, 101)),
                                           ("usage_wrap_up", OptionKey.STOP_WORDS_WEEKLY, 99, (0, 101)),
                                           ("usage_meter", OptionKey.WARN_WEEKLY, 1, (0, 101)),
                                           ("usage_pause", OptionKey.PAUSE_FIVE_HOUR, 100, (0, 101)),
                                           ("usage_meter", OptionKey.POLL_MINUTES, 7, (4, 61))):
            with self.subTest(key=key):
                self.assertTrue(self.set(capability, key, good)["done"])
                self.assertEqual(self.rt.state.options(capability)[key], good)
                for value in (*bad, "93", 93.0):
                    self.assertEqual(self.set(capability, key, value)["refusal"], Refusal.OPTION_INVALID, value)
        self.assertEqual(self.set("usage_wrap_up", OptionKey.WRAP_STYLE, 9)["refusal"], Refusal.OPTION_INVALID,
                         "a choice with no custom range takes its presets alone")
        listed = {item["id"]: item for item in self.rt.arming.listing()["capabilities"]}
        options = {option["key"]: option for option in listed["usage_meter"]["options"]}
        self.assertEqual((options["poll_minutes"]["custom"], options["warn_weekly"]["custom"]), ([5, 60], [1, 100]))
        self.assertNotIn("custom", options["window_weekly"])

    def test_each_windows_percentages_stay_in_order_and_a_forced_stop_below_the_words_only_warns(self):
        """v0.6.16-beta.4 (j): warn <= wrap-up < the words' stop, each window on its own - refused otherwise, with
        nothing written; a forced stop below the words' stop is taken, and said (it may cut Codex off first)."""
        for capability, key, value in (("usage_meter", OptionKey.WARN_FIVE_HOUR, 91),
                                       ("usage_wrap_up", OptionKey.WRAP_WEEKLY, 95),
                                       ("usage_wrap_up", OptionKey.STOP_WORDS_FIVE_HOUR, 90),
                                       ("usage_wrap_up", OptionKey.WRAP_FIVE_HOUR, 84)):
            with self.subTest(key=key):
                before = self.rt.state.options(capability)[key]
                found = self.set(capability, key, value)
                if key == OptionKey.WRAP_FIVE_HOUR:
                    self.assertEqual(found["refusal"], Refusal.OPTION_ORDER, "below the warning, 85")
                else:
                    self.assertEqual(found["refusal"], Refusal.OPTION_ORDER)
                self.assertEqual(self.rt.state.options(capability)[key], before)
        self.assertTrue(self.set("usage_meter", OptionKey.WARN_FIVE_HOUR, 90)["done"], "at the wrap-up is in order")
        self.assertTrue(self.set("usage_wrap_up", OptionKey.STOP_WORDS_WEEKLY, 91)["done"])
        found = self.set("usage_pause", OptionKey.PAUSE_FIVE_HOUR, 92)
        self.assertEqual((found["done"], found.get("warning")), (True, "stop_before_words"))
        self.assertEqual(self.rt.state.options("usage_pause")[OptionKey.PAUSE_FIVE_HOUR], 92)
        self.assertNotIn("warning", self.set("usage_pause", OptionKey.PAUSE_FIVE_HOUR, 97))

    def test_a_value_stored_out_of_order_by_an_older_beta_blocks_only_changes_to_its_own_window(self):
        """beta.3 took any preset with no order check: a wrap-up at 96, at or above the words' 95, may be stored. A
        change elsewhere - the spacing, the other window - is taken; one to that window must leave it in order."""
        state = self.rt.state
        state.set_option("usage_wrap_up", OptionKey.WRAP_FIVE_HOUR, 96, generation=state.meta()["generation"],
                         actor=Actor.DASHBOARD)
        self.assertTrue(self.set("usage_meter", OptionKey.POLL_MINUTES, 30)["done"], "the spacing")
        self.assertTrue(self.set("usage_wrap_up", OptionKey.WRAP_WEEKLY, 88)["done"], "the other window")
        self.assertTrue(self.set("usage_wrap_up", OptionKey.WRAP_STYLE, 2)["done"], "the wording")
        self.assertEqual(self.set("usage_meter", OptionKey.WARN_FIVE_HOUR, 80)["refusal"], Refusal.OPTION_ORDER,
                         "its own window is still checked")
        self.assertTrue(self.set("usage_wrap_up", OptionKey.WRAP_FIVE_HOUR, 94)["done"], "and may be put in order")

    def test_the_meter_reads_at_a_spacing_typed_in(self):
        self.on("usage_meter")
        self.assertTrue(self.set("usage_meter", OptionKey.POLL_MINUTES, 7)["done"])
        self.look()
        self.now += 6 * 60
        self.look()
        self.assertEqual(len(self.calls), 1)
        self.now += 61
        self.look()
        self.assertEqual(len(self.calls), 2, "at seven minutes, as typed in")


class MeterTests(UsageCase):
    def window_off(self, key, capability="usage_meter", value=2):
        """(e): one window switched off - or, with `value` 1, on - in a capability's own choices, as the Dashboard sets
        it."""
        result = self.rt.arming.set_option(capability, key, value, generation=self.rt.state.meta()["generation"],
                                           actor=Actor.DASHBOARD)
        self.assertTrue(result["done"], result)

    def test_each_stage_is_banded_by_its_own_window_switches(self):
        """v0.6.16 final: the meter's five-hour switch off stops only its warning - the wrap-up, its own switch on,
        still bands the window; the wrap-up's own switch off, it bands nothing there."""
        self.on("usage_meter", "usage_wrap_up")
        self.window_off(OptionKey.WINDOW_FIVE_HOUR)
        self.answer = reply(five=92, week=92)
        self.look()
        self.assertIsNone(self.rt.state.meter()[("codex", 300)]["warned_reset_at"], "the meter's own: no warning")
        bands = {row["window_minutes"]: row["band"] for row in surfaces.meter_view(self.rt)["meter"]["windows"]}
        self.assertEqual(bands, {300: "wrap_up", 10080: "wrap_up"})
        self.window_off(OptionKey.WINDOW_FIVE_HOUR, "usage_wrap_up")
        bands = {row["window_minutes"]: row["band"] for row in surfaces.meter_view(self.rt)["meter"]["windows"]}
        self.assertEqual(bands, {300: "none", 10080: "wrap_up"})

    def test_a_window_switched_off_is_shown_never_warned_of(self):
        """v0.6.16-beta.4 (e): the five-hour window off - read and shown, no warning, no band; the weekly one acts."""
        self.on("usage_meter")
        self.window_off(OptionKey.WINDOW_FIVE_HOUR)
        self.answer = reply(five=96, week=96)
        self.look()
        meter = self.rt.state.meter()
        self.assertEqual(meter[("codex", 300)]["used_percent"], 96.0, "still read and shown")
        self.assertIsNone(meter[("codex", 300)]["warned_reset_at"])
        self.assertIsNotNone(meter[("codex", 10080)]["warned_reset_at"])
        bands = {row["window_minutes"]: row["band"] for row in surfaces.meter_view(self.rt)["meter"]["windows"]}
        self.assertEqual(bands, {300: "none", 10080: "warn"})

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
        self.answer = reply(five=98)
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

    def test_a_window_switched_off_is_never_held_and_one_held_lets_go(self):
        """v0.6.16-beta.4 (e): over the stop percentage with its window switched off - in its own choices from v0.6.16
        final - nothing is held; a window held lets go as soon as it is switched off."""
        self.on("usage_pause")
        self.answer = reply(five=98)
        self.look()
        self.look()
        self.assertIs(self.rt.ask(Point.GATES, "usage", self.CORE, {}), Alternative.HOLD)
        MeterTests.window_off(self, OptionKey.WINDOW_FIVE_HOUR, "usage_pause")
        self.look()
        self.assertIs(self.rt.ask(Point.GATES, "usage", self.CORE, {}), DEFER)
        self.now += 20 * 60
        self.look()
        self.look()
        self.assertIs(self.rt.ask(Point.GATES, "usage", self.CORE, {}), DEFER, "never held while off")

    def test_the_meters_window_switch_leaves_the_stop_alone(self):
        """v0.6.16 final: the meter's own five-hour switch decides only its warnings - with it off, the window over the
        stop percentage is held all the same."""
        self.on("usage_pause")
        MeterTests.window_off(self, OptionKey.WINDOW_FIVE_HOUR)
        self.answer = reply(five=98)
        self.look()
        self.look()
        self.assertIs(self.rt.ask(Point.GATES, "usage", self.CORE, {}), Alternative.HOLD)

    def test_below_the_percentage_nothing_is_held(self):
        self.on("usage_pause")
        self.answer = reply(five=96)
        self.look()
        self.look()
        self.assertIs(self.rt.ask(Point.GATES, "usage", self.CORE, {}), DEFER)

    def test_off_nothing_is_held(self):
        self.on("usage_meter")
        self.answer = reply(five=99)
        self.look()
        self.look()
        self.assertIs(self.rt.ask(Point.GATES, "usage", self.CORE, {}), DEFER)


class PauseBesideResetCreditTests(UsageCase):
    """The pause and a reset credit, v0.6.17's P-8.

    A credit resets the window there and then and buys fifteen minutes in which every waiting recovery
    is looked at early (engine/credits.py, P7 EARLY). The pause's own mark moves only on a reading of
    the meter's, and the meter reads while the Codex app runs, every Poll minutes - so with the app
    closed the pause held every record through the whole early window and on to the reset the credit
    was spent to avoid: the credit bought nothing. Each test here drives the broken case, the meter not
    reading."""

    CORE = {"interruption_id": ac.KEY, "thread_id": ac.THREAD}

    def setUp(self):
        super().setUp()
        self.occasion = 0

    def credit(self, minutes=300, *, outcome=SpendOutcome.RESET, bucket="codex"):
        """One reset credit of this edition's spent on a window and answered, as engine/credits.py
        writes it (state/resets: the spend first, its outcome when Codex answers)."""
        self.occasion += 1
        state = self.rt.state
        spend = state.add_credit_spend(1, bucket, minutes, self.occasion, str(uuid.uuid4()), at=self.now)
        self.assertIsNotNone(spend)
        self.assertTrue(state.finish_credit_spend(spend, outcome, at=self.now))
        return spend

    def held(self, five=98, week=20.0):
        """The pause holding, and then the Codex app closed: the meter reads nothing more."""
        self.on("usage_pause")
        self.answer = reply(five=five, week=week)
        self.look()
        self.look()
        self.assertIs(self.rt.ask(Point.GATES, "usage", self.CORE, {}), Alternative.HOLD)
        self.app = False
        self.now += 60

    def test_a_reset_credit_of_the_held_window_lets_the_early_window_be_used(self):
        self.held()
        self.credit()
        self.assertIs(self.rt.ask(Point.GATES, "usage", self.CORE, {}), DEFER,
                      "the credit reset the window: nothing waits for the reset it paid to avoid")
        self.assertFalse(self.rt._code_of(USAGE_PAUSE).holds({"state": "waiting", "purpose": "continuation"}))
        self.look()
        self.assertIsNone(self.rt.state.meter()[("codex", 300)]["paused_reset_at"], "the mark is let go")
        self.assertIn("pause.resumed", [line["code"] for line in self.rt.state.journal()])

    def test_the_pause_still_holds_where_no_credit_was_spent(self):
        self.held()
        self.now += 600
        self.look()
        self.assertIs(self.rt.ask(Point.GATES, "usage", self.CORE, {}), Alternative.HOLD)
        self.assertTrue(self.rt._code_of(USAGE_PAUSE).holds({"state": "waiting", "purpose": "continuation"}))
        self.assertIsNotNone(self.rt.state.meter()[("codex", 300)]["paused_reset_at"])

    def test_a_credit_for_another_window_leaves_this_ones_pause_standing(self):
        self.held(five=98, week=98)
        self.credit(minutes=usage.WEEKLY)
        self.assertIs(self.rt.ask(Point.GATES, "usage", self.CORE, {}), Alternative.HOLD,
                      "the five-hour window was not the one the credit reset")
        self.look()
        rows = self.rt.state.meter()
        self.assertIsNone(rows[("codex", usage.WEEKLY)]["paused_reset_at"])
        self.assertIsNotNone(rows[("codex", 300)]["paused_reset_at"])
        self.assertIs(self.rt.ask(Point.GATES, "usage", self.CORE, {}), Alternative.HOLD)

    def test_a_credit_spent_before_the_reading_the_pause_rests_on_holds_nothing_back(self):
        """A credit of an earlier filling of the window: the meter read the window full after it, so the
        reading stands and the pause with it."""
        self.on("usage_pause")
        self.credit()
        self.now += 60
        self.answer = reply(five=98)
        self.look()
        self.look()
        self.app = False
        self.now += 600
        self.assertIs(self.rt.ask(Point.GATES, "usage", self.CORE, {}), Alternative.HOLD)


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
        self.language(plug, "en")
        for _ in range(3):
            self.h.tick(advance=61)
        sent = [prompt for thread, prompt in self.h.backend.send_calls if thread == T1]
        self.assertEqual(len(sent), 1, self.h.logs[-10:])
        self.assertTrue(sent[0].startswith(statement.CATALOGS.text("continue.wrap_up.standard", "en")))
        for _ in range(3):
            self.h.tick(advance=61)
        self.assertEqual(len([t for t, _p in self.h.backend.send_calls if t == T1]), 1, "once for the window")

    def language(self, plug, locale):
        """The continuation language a person chose, written where core keeps it - never this PC's own."""
        from codex_auto_resume import settings
        values = settings.defaults()
        values["continuation_language"] = locale
        settings.save(plug.paths.settings_file, values)

    def test_with_the_numbers_the_words_name_the_window_and_the_stop_percentage(self):
        """v0.6.16-beta.4 (c, d, j): the wording with the numbers says how much of which window is used and the stop
        percentage the person chose for that window - the five-hour one's here, 96 - in the words sent."""
        plug, _turn = self.running()
        self.language(plug, "en")
        self.choose(plug, OptionKey.WRAP_STYLE, 4)
        self.choose(plug, OptionKey.STOP_WORDS_FIVE_HOUR, 96)
        for _ in range(3):
            self.h.tick(advance=61)
        sent = [prompt for thread, prompt in self.h.backend.send_calls if thread == T1]
        self.assertEqual(len(sent), 1, self.h.logs[-10:])
        expected = statement.CATALOGS.text("continue.wrap_up.numbers", "en", percent=91,
                                           window=statement.CATALOGS.text("continue.wrap_up.window.five_hour", "en"),
                                           stop_at=96)
        self.assertTrue(sent[0].startswith(expected), sent[0])

    def test_the_weekly_window_is_named_as_this_weeks_limit(self):
        plug, _turn = self.running(percent=50)
        self.language(plug, "en")
        self.choose(plug, OptionKey.WRAP_STYLE, 4)
        plug.runtime.state.save_meter([{"bucket": "codex", "window_minutes": 10080, "used_percent": 92,
                                        "reset_at": int(self.h.now) + 86400}], at=self.h.now)
        for _ in range(3):
            self.h.tick(advance=61)
        sent = [prompt for thread, prompt in self.h.backend.send_calls if thread == T1]
        self.assertEqual(len(sent), 1, self.h.logs[-10:])
        self.assertIn(statement.CATALOGS.text("continue.wrap_up.window.weekly", "en"), sent[0])
        self.assertIn("95%", sent[0])

    def test_the_words_are_in_the_continuation_language(self):
        """Sent in the language a person chose for continuations, whatever the window's - core's resolve_locale."""
        plug, _turn = self.running()
        self.choose(plug, OptionKey.WRAP_STYLE, 4)
        self.language(plug, "ko")
        for _ in range(3):
            self.h.tick(advance=61)
        sent = [prompt for thread, prompt in self.h.backend.send_calls if thread == T1]
        self.assertEqual(len(sent), 1, self.h.logs[-10:])
        self.assertIn(statement.CATALOGS.text("continue.wrap_up.window.five_hour", "ko"), sent[0])

    def wrapped_then(self, status, *, after_reset=None):
        """A wrap-up sent and delivered - Codex runs it as a turn of its own - that turn ended with `status`, and then
        the window's reset passed, with a reading of the new window. What is sent after the wrap-up."""
        plug, turn = self.running()
        self.language(plug, "en")
        if after_reset is not None:
            self.choose(plug, OptionKey.WRAP_AFTER_RESET, after_reset)
        self.h.backend.after_accept = "queue"
        self.h.tick(advance=61)
        self.h.tick(advance=61)
        wrapped = len(self.h.backend.send_calls)
        self.h.home.set_turn(T1, turn, status="completed", completed_at=int(self.h.now))
        delivered = self.h.home.dispatch(T1, status=status, progress=True)
        for _ in range(3):
            self.h.tick(advance=61)
        reset = plug.runtime.state.meter()[("codex", 300)]["reset_at"]
        self.h.now = reset + 120
        plug.runtime.state.save_meter([{"bucket": "codex", "window_minutes": 300, "used_percent": 2,
                                        "reset_at": reset + 5 * 3600}], at=self.h.now)
        for _ in range(4):
            self.h.tick(advance=61)
        return plug, wrapped, delivered, self.h.backend.send_calls[wrapped:]

    def test_continue_after_the_reset_sends_one_continuation_to_a_conversation_that_ended_well(self):
        """v0.6.16-beta.4 (g): wrapped up, then ended well before the limit - once the window resets, one continuation,
        through core's queue, in the continuation language."""
        plug, wrapped, delivered, after = self.wrapped_then("completed")
        self.assertEqual(wrapped, 1)
        self.assertIsNotNone(delivered)
        self.assertEqual(len(after), 1, self.h.logs[-12:])
        self.assertTrue(after[0][1].startswith(statement.CATALOGS.text("continue.after_reset", "en") + "\n\n"))
        self.assertIn("wrap.continued", [entry["code"] for entry in plug.runtime.state.journal()])
        for _ in range(4):
            self.h.tick(advance=61)
        self.assertEqual(len(self.h.backend.send_calls), wrapped + 1, "once")

    def test_after_the_reset_a_failed_turn_is_cores_and_the_choice_off_sends_nothing(self):
        _plug, wrapped, _delivered, after = self.wrapped_then("completed", after_reset=2)
        self.assertEqual(after, [], "Continue after the reset off")
        self.setUp()
        _plug, wrapped, _delivered, after = self.wrapped_then("interrupted")
        self.assertEqual(after, [], "a turn stopped is not the wrap-up's to continue")

    def test_after_the_reset_newer_work_of_the_person_wins_and_nothing_is_sent(self):
        """A17: a turn of the person's own after the wrap-up's turn - nothing is queued onto it after the reset."""
        plug, turn = self.running()
        self.language(plug, "en")
        self.h.backend.after_accept = "queue"
        self.h.tick(advance=61)
        self.h.tick(advance=61)
        wrapped = len(self.h.backend.send_calls)
        self.assertEqual(wrapped, 1)
        self.h.home.set_turn(T1, turn, status="completed", completed_at=int(self.h.now))
        self.h.home.dispatch(T1, status="completed", progress=True)
        for _ in range(3):
            self.h.tick(advance=61)
        self.h.home.add_turn(T1, user_text="my own newer question")
        for _ in range(2):
            self.h.tick(advance=61)
        reset = plug.runtime.state.meter()[("codex", 300)]["reset_at"]
        self.h.now = reset + 120
        plug.runtime.state.save_meter([{"bucket": "codex", "window_minutes": 300, "used_percent": 2,
                                        "reset_at": reset + 5 * 3600}], at=self.h.now)
        for _ in range(4):
            self.h.tick(advance=61)
        self.assertEqual(self.h.backend.send_calls[wrapped:], [])
        reasons = [row["reason"] for row in plug.runtime.state.continuations(capability=self.cap, pending=None)
                   if row["kind"] == "after_reset"]
        self.assertEqual(reasons, ["superseded"])

    def window(self, plug, capability, key, value=2):
        result = plug.runtime.arming.set_option(capability, key, value,
                                                generation=plug.runtime.state.meta()["generation"], actor=Actor.DASHBOARD)
        self.assertTrue(result["done"], result)

    def test_a_window_switched_off_gets_no_wrap_up(self):
        """v0.6.16-beta.4 (e): the five-hour window over its wrap-up percentage but switched off - in the wrap-up's own
        choices from v0.6.16 final - nothing is sent."""
        plug, _turn = self.running()
        self.window(plug, "usage_wrap_up", OptionKey.WINDOW_FIVE_HOUR)
        for _ in range(3):
            self.h.tick(advance=61)
        self.assertEqual(self.h.backend.send_calls, [])
        self.assertEqual(plug.runtime.state.continuations(capability=self.cap, pending=None), [])

    def test_both_windows_off_it_acts_on_neither(self):
        """v0.6.16 final: the wrap-up with both its windows switched off sends nothing for either, though both are
        over its percentage; the meter still reads and shows them."""
        plug, _turn = self.running()
        plug.runtime.state.save_meter([{"bucket": "codex", "window_minutes": 300, "used_percent": 91,
                                        "reset_at": int(self.h.now) + 3600},
                                       {"bucket": "codex", "window_minutes": 10080, "used_percent": 91,
                                        "reset_at": int(self.h.now) + 86400}], at=self.h.now)
        self.window(plug, "usage_wrap_up", OptionKey.WINDOW_FIVE_HOUR)
        self.window(plug, "usage_wrap_up", OptionKey.WINDOW_WEEKLY)
        for _ in range(3):
            self.h.tick(advance=61)
        self.assertEqual(self.h.backend.send_calls, [])
        self.assertEqual(usage.acting(plug.runtime.state.options("usage_wrap_up")), frozenset())
        self.assertEqual({minutes for (_bucket, minutes) in plug.runtime.state.meter()}, {300, 10080})

    def test_the_meters_window_switch_leaves_the_wrap_up_alone(self):
        """v0.6.16 final: the meter's own five-hour switch off stops only its warnings - the wrap-up is still sent."""
        plug, _turn = self.running()
        self.window(plug, "usage_meter", OptionKey.WINDOW_FIVE_HOUR)
        for _ in range(3):
            self.h.tick(advance=61)
        self.assertEqual(len([t for t, _p in self.h.backend.send_calls if t == T1]), 1, self.h.logs[-10:])

    def test_include_the_reset_time_says_when_the_window_resets_and_off_leaves_it_out(self):
        """v0.6.16-beta.4 (i): on by default, the words end with when the window that triggered them resets - core's hour
        and minute for the five-hour window; switched off, nothing is added."""
        from codex_auto_resume import continuation
        plug, _turn = self.running()
        self.language(plug, "en")
        reset = int(self.h.now) + 3600
        for _ in range(3):
            self.h.tick(advance=61)
        (sent,) = [prompt for thread, prompt in self.h.backend.send_calls if thread == T1]
        said = statement.CATALOGS.text("continue.wrap_up.resets_at", "en", reset=continuation.format_reset_time(reset))
        self.assertIn(statement.CATALOGS.text("continue.wrap_up.standard", "en") + " " + said, sent)
        self.setUp()
        plug, _turn = self.running()
        self.language(plug, "en")
        self.choose(plug, OptionKey.WRAP_RESET_TIME, 2)
        for _ in range(3):
            self.h.tick(advance=61)
        (sent,) = [prompt for thread, prompt in self.h.backend.send_calls if thread == T1]
        self.assertNotIn(statement.CATALOGS.text("continue.wrap_up.resets_at", "en", reset="").split("{")[0][:12], sent)

    def test_what_the_page_shows_under_the_choice_is_what_is_sent(self):
        """v0.6.16-beta.4 (a): the words advanced-wordings shows for a window (usage.previews) are the words sent."""
        plug, _turn = self.running()
        self.language(plug, "en")
        self.choose(plug, OptionKey.WRAP_STYLE, 4)
        shown = plug.runtime.arming.wordings_view("usage_wrap_up")["previews"]
        self.assertEqual(set(shown), {"300", "10080"})
        for _ in range(3):
            self.h.tick(advance=61)
        (sent,) = [prompt for thread, prompt in self.h.backend.send_calls if thread == T1]
        self.assertTrue(sent.startswith(shown["300"] + "\n"), (sent, shown["300"]))

    def test_custom_the_windows_own_words_are_sent_filled_in(self):
        """v0.6.16-beta.4 (b): with Custom, a window's own words, the numbers filled in (test_advanced_wordings)."""
        plug, _turn = self.running()
        self.language(plug, "en")
        self.choose(plug, OptionKey.WRAP_STYLE, wrapwords.CUSTOM_STYLE)
        state = plug.runtime.state
        assert plug.runtime.arming.set_wording("usage_wrap_up", "wrap_custom_five_hour",
                                               "Finish now: {percent}% of {window}.",
                                               generation=state.meta()["generation"], actor=Actor.DASHBOARD)["done"]
        for _ in range(3):
            self.h.tick(advance=61)
        (sent,) = [prompt for thread, prompt in self.h.backend.send_calls if thread == T1]
        self.assertTrue(sent.startswith("Finish now: 91% of the five-hour limit."), sent)

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

    def _limit_story(self, percent):
        """The turn running fails at the usage limit; with a wrap-up queued (91%) Codex delivers it into a turn of its
        own, which fails at the limit as well. Then the reset passes."""
        from test_engine import dispatch_and_fail, fail_turn
        _plug, turn = self.running(percent=percent)
        self.h.backend.after_accept = "queue"
        self.h.tick(advance=61)
        self.h.tick(advance=61)
        wrapped = len(self.h.backend.send_calls)
        reset = int(self.h.now) + 600
        fail_turn(self.h.home, T1, turn, usage=True, reset=reset)
        self.h.tick(advance=1)
        if wrapped:
            dispatch_and_fail(self.h.home, T1, usage=True, reset=reset)
        for _ in range(3):
            self.h.tick(advance=5)
        self.h.now = reset + 120
        for _ in range(60):
            self.h.tick(advance=30)
        return wrapped, len(self.h.backend.send_calls) - wrapped, [row["state"] for row in self.h.records(T1)]

    def test_a_wrap_up_turn_is_the_products_own_and_the_recovery_ends_as_without_it(self):
        """The turn a wrap-up starts is this product's own message, never the person's work (A17): the failure before
        it is superseded as no longer the latest - not superseded_by_user - and the conversation is recovered once
        after the reset, as it is with no wrap-up."""
        _wrapped, control_sends, control = self._limit_story(80)
        self.setUp()
        wrapped, sends, states = self._limit_story(91)
        self.assertEqual(wrapped, 1)
        self.assertEqual(sends, control_sends)
        self.assertEqual(control_sends, 1)
        self.assertNotIn("superseded_by_user", states)
        self.assertEqual(states, ["superseded"] + control)


if __name__ == "__main__":
    unittest.main()
