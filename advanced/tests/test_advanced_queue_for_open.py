"""Queue for opening (v0.6.15-beta): a usage-limited conversation the app does not hold is queued in Codex for when the
person opens it, for the Days they chose, once - and the capability turns off where Codex did not run it on open.

Held against the shipped definition and statement and against core's own engine, store and simulated Codex home
(takingcase.py).

    PYTHONPATH=src python -m unittest discover -s advanced/tests
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from takingcase import TakingCase  # noqa: E402
from advancedcase import ENGINE  # noqa: E402
from codex_auto_resume import machine  # noqa: E402
from codex_auto_resume.domain.plug import DEFER, Alternative, Point  # noqa: E402
from codex_auto_resume_advanced import registry  # noqa: E402
from codex_auto_resume_advanced.engine.foropen import QueueForOpen  # noqa: E402
from codex_auto_resume_advanced.registry import QUEUE_FOR_OPEN  # noqa: E402
from codex_auto_resume_advanced.vocabulary import (Actor, ArmingState, ArmingWarning, JournalCode, Measurement,  # noqa: E402
                                                   OffReason, OptionKey, OverrideKind, Verdict)
from test_engine import T1  # noqa: E402

DAY = 86400


class ForOpenCase(TakingCase):
    DEFINITION = QUEUE_FOR_OPEN

    def arm(self, plug, state="armed", capability=None, **changes):
        """Armed as a person arms it: confirming the warnings its statement shows - M1 unmeasured on this Codex."""
        definition = plug.runtime.registry.get(capability or self.cap)
        changes.setdefault("warnings", [str(word) for word in plug.runtime.arming.warnings(definition)])
        return super().arm(plug, state=state, capability=capability, **changes)

    def due(self, h=None):
        """A usage-limited conversation the app does not hold, past its reset."""
        h = h or self.h
        self.ready_after_reset(h, loaded=False)
        h.backend.loaded_map[T1] = "notLoaded"
        h.backend.after_accept = "queue"

    def queued(self, plug=None, h=None):
        h = h or self.h
        plug = plug or self.armed(h)
        self.due(h)
        h.tick()
        row = h.record()
        self.assertEqual(row["state"], "queued", row["last_error"])
        self.assertEqual(len(h.backend.send_calls), 1)
        return plug, row

    def override(self, plug, row):
        return plug.runtime.state.override(row["interruption_id"], self.cap)


class QueueTests(ForOpenCase):
    def test_off_it_waits_for_the_app_as_the_standard_edition_does(self):
        self.plugged(self.advanced())
        self.due()
        self.h.tick()
        self.assertEqual(self.h.backend.send_calls, [])
        self.assertEqual(self.h.record()["last_error"], "notLoaded")

    def test_watched_it_only_journals(self):
        plug = self.armed(state="shadow")
        self.due()
        self.h.tick()
        self.assertEqual(self.h.backend.send_calls, [])
        self.assertIn((JournalCode.WOULD_HAVE, Point.UNLOADED, Alternative.QUEUE_FOR_OPEN), self.journal(plug))

    def test_on_it_is_queued_once_paid_for_in_the_claim(self):
        plug, row = self.queued()
        found = self.override(plug, row)
        self.assertEqual(found["kind"], OverrideKind.QUEUE_FOR_OPEN)
        self.assertEqual(found["created_at"], self.h.now, "written in the claim that paid for it")
        self.assertEqual([spend[0] for spend in self.spends(plug)], [self.cap])
        self.assertEqual(machine.decode_gates(row["gate_eval"])["thread_available"], (machine.PASS, machine.PLUGGED))

    def test_it_is_kept_for_the_days_chosen_and_then_taken_back_and_never_queued_again(self):
        plug, row = self.queued()
        for _ in range(2 * 24):
            self.h.tick(advance=3600)
        self.assertEqual(self.h.record()["state"], "queued", "two days: kept")
        for _ in range(2 * 24):
            self.h.tick(advance=3600)
        reasons = [event.get("reason") for event in self.h.store.events(row["interruption_id"])]
        self.assertIn("window_ended", reasons, "taken back once the Days ran out")
        for _ in range(10):
            self.h.tick(advance=60)
        self.assertIn(self.h.record()["state"], machine.WAITING)
        self.assertEqual(len(self.h.backend.send_calls), 1, "one queueing an interruption: it waits for the app now")
        self.assertEqual(self.h.record()["last_error"], "notLoaded", "as A11 says - not held by the ledger's refusal")

    def test_the_days_option_keeps_it_longer(self):
        plug = self.armed()
        self.choose(plug, OptionKey.DAYS, 5)
        plug, row = self.queued(plug)
        for _ in range(4 * 24):
            self.h.tick(advance=3600)
        self.assertEqual(self.h.record()["state"], "queued", "four days of five")

    def test_turned_off_it_is_taken_back_at_the_next_look(self):
        plug, row = self.queued()
        self.assertTrue(plug.runtime.arming.disarm(self.cap, actor=Actor.DASHBOARD)["done"])
        plug.runtime.states(fresh=True)
        self.h.watch(advance=61)
        self.assertEqual((self.h.record()["state"], self.h.record()["last_error"]),
                         ("withdrawn_unconfirmed", "window_ended"))

    def test_the_goal_route_answers_first_where_both_are_on(self):
        ids = [definition.id for definition in registry.DEFINITIONS]
        self.assertLess(ids.index("goal_continuation"), ids.index(self.cap))
        self.assertEqual(tuple(d.id for d in registry.REGISTRY.at(Point.UNLOADED)),
                         ("goal_continuation", "queue_for_open", "compact_continue", "headless_run",
                          "other_sessions"))


class TripwireTests(ForOpenCase):
    def test_opened_and_not_run_turns_it_off(self):
        """Fails with the tripwire reverted: Codex not delivering on open would leave it on."""
        plug, row = self.queued()
        self.h.backend.loaded_map[T1] = "loaded"         # opened, and Codex does not run the queue head
        self.h.watch(advance=6)
        self.h.watch(advance=200)
        self.assertEqual(self.h.record()["withdraw_reason"], "not_delivered_on_open")
        states = plug.runtime.states(fresh=True)
        self.assertEqual(states.get(self.cap, ArmingState.OFF), ArmingState.OFF)
        self.assertEqual(plug.runtime.state.arming()[self.cap]["reason"], OffReason.NOT_DELIVERED_ON_OPEN)

    def test_unmeasured_on_this_codex_is_a_warning_to_confirm_never_a_refusal(self):
        plug = self.advanced()
        definition = plug.runtime.registry.get(self.cap)
        self.assertIn(ArmingWarning.UNMEASURED, plug.runtime.arming.warnings(definition))
        self.measured = {Measurement.M1: (Verdict.PASS, ENGINE)}
        self.assertNotIn(ArmingWarning.UNMEASURED, plug.runtime.arming.warnings(definition))
        self.measured = {}
        self.arm(plug)
        self.assertEqual(plug.runtime.states(fresh=True)[self.cap], ArmingState.ARMED)


class CodeTests(unittest.TestCase):
    def test_unbound_or_unreadable_it_answers_nothing(self):
        code = QueueForOpen(None)
        self.assertIs(code.unloaded({"interruption_id": "%064x" % 1}), DEFER)


if __name__ == "__main__":
    unittest.main()
