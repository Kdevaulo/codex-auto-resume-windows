"""Other sessions (v0.6.16-beta.4): the conversations of a terminal's Codex TUI and of VS Code are watched and
recovered too while a person has it on - sent through the queue where another Codex session holds one - and the
capability turns off where such a session did not take what was sent to it.

Held against the shipped definition and statement and against core's own engine, store and simulated Codex home
(takingcase.py; the conversations of the other kinds as tests/test_session_kinds writes them).

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
from codex_auto_resume_advanced.engine.sessions import OtherSessions  # noqa: E402
from codex_auto_resume_advanced.registry import OTHER_SESSIONS  # noqa: E402
from codex_auto_resume_advanced.vocabulary import (Actor, ArmingState, ArmingWarning, JournalCode,  # noqa: E402
                                                   Measurement, OffReason, Refusal, Verdict)
from test_engine import T1, T2  # noqa: E402
from test_session_kinds import CLI, IDE, add_thread  # noqa: E402


class SessionsCase(TakingCase):
    DEFINITION = OTHER_SESSIONS

    def arm(self, plug, state="armed", capability=None, **changes):
        """Armed as a person arms it: confirming the warnings its statement shows - M5 and MO unmeasured here."""
        definition = plug.runtime.registry.get(capability or self.cap)
        changes.setdefault("warnings", [str(word) for word in plug.runtime.arming.warnings(definition)])
        return super().arm(plug, state=state, capability=capability, **changes)

    def other(self, thread_id, kind, h=None):
        """A usage limit in a conversation of a terminal's TUI or of VS Code, past its reset, held by the app."""
        h = h or self.h
        add_thread(h.home, thread_id, **kind)
        self.ready_after_reset(h, thread_id=thread_id)

    def queued(self, plug=None):
        """A usage-limited conversation another Codex session holds, sent for that session to take."""
        plug = plug or self.armed()
        self.ready_after_reset(self.h, loaded=False)
        self.h.backend.loaded_map[T1] = "elsewhere"
        self.h.backend.after_accept = "queue"
        self.h.tick()
        row = self.h.record()
        self.assertEqual(row["state"], "queued", row["last_error"])
        return plug, row


class KindsTests(SessionsCase):
    def test_off_only_the_apps_conversations_are_watched(self):
        self.plugged(self.advanced())
        self.other(T1, CLI)
        self.h.tick()
        self.assertEqual(self.h.records(T1), [])

    def test_on_a_terminals_and_vs_codes_conversations_are_recovered(self):
        """Fails with its P18 answer reverted: neither would be detected."""
        self.armed()
        self.other(T1, CLI)
        self.other(T2, IDE)
        self.h.tick()
        self.assertEqual(len(self.h.records(T1)), 1)
        self.assertEqual(len(self.h.records(T2)), 1)

    def test_watched_it_only_journals(self):
        plug = self.armed(state="shadow")
        self.other(T1, CLI)
        self.h.tick()
        self.assertEqual(self.h.records(T1), [])
        self.assertIn((JournalCode.WOULD_HAVE, Point.SESSIONS, Point.SESSIONS), self.journal(plug))

    def test_turned_off_the_waiting_records_of_those_conversations_are_cancelled(self):
        plug = self.armed()
        add_thread(self.h.home, T1, **CLI)
        self.h.home.fail_usage(T1)
        self.h.tick()
        self.assertIn(self.h.record(T1)["state"], machine.WAITING)
        self.assertTrue(plug.runtime.arming.disarm(self.cap, actor=Actor.DASHBOARD)["done"])
        plug.runtime.states(fresh=True)
        self.h.tick(advance=1)
        row = self.h.record(T1)
        self.assertEqual((row["state"], row["last_error"]), ("cancelled", "session_kind_off"))


class SendTests(SessionsCase):
    def test_off_it_waits_while_another_session_holds_it(self):
        self.plugged(self.advanced())
        self.ready_after_reset(self.h, loaded=False)
        self.h.backend.loaded_map[T1] = "elsewhere"
        self.h.tick()
        self.assertEqual(self.h.backend.send_calls, [])
        self.assertEqual(self.h.record()["last_error"], "held_by_other_session")

    def test_on_it_is_sent_for_that_session_to_take(self):
        plug, row = self.queued()
        self.assertEqual(len(self.h.backend.send_calls), 1)
        self.assertEqual(machine.decode_gates(row["gate_eval"])["thread_available"], (machine.PASS, machine.SESSION))
        self.assertEqual([spend[0] for spend in self.spends(plug)], [self.cap], "paid for in the claim")

    def test_it_answers_after_the_routes_before_it(self):
        ids = [definition.id for definition in registry.DEFINITIONS]
        self.assertLess(ids.index("headless_run"), ids.index(self.cap))
        self.assertEqual(tuple(d.id for d in registry.REGISTRY.at(Point.SESSIONS)), (self.cap,))
        shown = registry.SHOWN_ORDER
        self.assertEqual(shown.index(self.cap), shown.index("headless_run") + 1)


class TripwireTests(SessionsCase):
    def test_not_taken_in_time_turns_it_off(self):
        """Fails with the tripwire reverted: a session that never takes what is queued would leave it on."""
        plug, row = self.queued()
        self.h.watch(advance=6)
        self.h.watch(advance=200)
        self.assertEqual(self.h.record()["withdraw_reason"], "not_delivered_on_open")
        states = plug.runtime.states(fresh=True)
        self.assertEqual(states.get(self.cap, ArmingState.OFF), ArmingState.OFF)
        self.assertEqual(plug.runtime.state.arming()[self.cap]["reason"], OffReason.NOT_DISPATCHED_BY_SESSION)

    def test_the_session_letting_go_does_not_turn_it_off(self):
        plug, row = self.queued()
        self.h.backend.loaded_map[T1] = "notLoaded"
        self.h.watch(advance=6)
        self.assertEqual(self.h.record()["withdraw_reason"], "window_ended")
        self.assertEqual(plug.runtime.states(fresh=True)[self.cap], ArmingState.ARMED)

    def test_it_may_not_be_kept_on(self):
        """Fails with keepable reverted: Keep on would make the tripwire a note."""
        plug = self.armed()
        runtime = plug.runtime
        refused = runtime.arming.set_keep_on(self.cap, True, generation=runtime.state.meta()["generation"],
                                             confirmed=["keep_on"], actor=Actor.DASHBOARD)
        self.assertEqual((refused["done"], refused["refusal"]), (False, Refusal.INVALID_REQUEST))
        self.assertIs(OTHER_SESSIONS.keepable, False)
        self.assertIn(OffReason.NOT_DISPATCHED_BY_SESSION, registry_tripwires())

    def test_unmeasured_on_this_codex_is_a_warning_to_confirm_never_a_refusal(self):
        plug = self.advanced()
        definition = plug.runtime.registry.get(self.cap)
        self.assertIn(ArmingWarning.UNMEASURED, plug.runtime.arming.warnings(definition))
        self.measured = {Measurement.M5: (Verdict.PASS, ENGINE), Measurement.MO: (Verdict.PASS, ENGINE)}
        self.assertNotIn(ArmingWarning.UNMEASURED, plug.runtime.arming.warnings(definition))
        self.measured = {}
        self.arm(plug)
        self.assertEqual(plug.runtime.states(fresh=True)[self.cap], ArmingState.ARMED)


def registry_tripwires():
    from codex_auto_resume_advanced.vocabulary import KEPT_NOTICES, TRIPWIRES
    return TRIPWIRES & frozenset(KEPT_NOTICES)


class CodeTests(unittest.TestCase):
    def test_it_names_both_kinds_and_answers_only_for_another_session(self):
        code = OtherSessions(None)
        self.assertEqual(code.sessions(), frozenset({"cli", "ide"}))
        self.assertIs(code.unloaded({"holder": "session", "app": True}), Alternative.TO_SESSION)
        for record in ({"holder": "none", "app": False}, {"holder": "session", "queued_since": 1}, None, "x"):
            self.assertIs(code.unloaded(record), DEFER, record)


if __name__ == "__main__":
    unittest.main()
