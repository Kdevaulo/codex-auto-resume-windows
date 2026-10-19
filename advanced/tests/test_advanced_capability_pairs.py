"""Two capabilities on at once, where one keeps the other from working (the v0.6.17 audit of capability pairs, the
owner's question after issue #42: "could other advanced capabilities overlap the way #42 did?").

Each test arms two shipped capabilities - their shipped definitions and statements - against core's own engine, store
and simulated Codex home (takingcase.py, test_advanced_goal.py), or against the runtime alone (advancedcase.py), and
asserts what a person who turned both on would expect. Each fails today, so each is marked expectedFailure with the
finding it shows; the fix that makes one pass removes its marker (an unexpected success fails the run).

    CODEX_AR_EDITION=advanced PYTHONPATH="src;advanced/src;tests" python -m unittest discover -s advanced/tests
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))

import advancedcase as ac  # noqa: E402
from takingcase import TakingCase  # noqa: E402
from test_advanced_goal import GoalCase  # noqa: E402
from test_advanced_usage import Session, UsageCase, reply  # noqa: E402
from codex_auto_resume.domain.plug import Alternative, Point  # noqa: E402
from codex_auto_resume import machine  # noqa: E402
from codex_auto_resume_advanced import runtime, statement  # noqa: E402
from codex_auto_resume_advanced.codex.turns import Turns  # noqa: E402
from codex_auto_resume_advanced.engine import foropen  # noqa: E402
from codex_auto_resume_advanced.registry import (COMPACT_CONTINUE, GOAL_CONTINUATION, MARKER_FREE,  # noqa: E402
                                                 OTHER_SESSIONS, QUEUE_FOR_OPEN, RESET_CREDIT, SILENT_CONTINUATION, USAGE_METER,
                                                 USAGE_PAUSE)
from codex_auto_resume_advanced.vocabulary import Actor, JournalCode, Measurement, SpendOutcome, Verdict  # noqa: E402
from advancedcase import ENGINE  # noqa: E402
from sessionsim import holding_sessions  # noqa: E402
from test_engine import T1  # noqa: E402

CONTEXT_FULL = json.dumps({"codexErrorInfo": "contextWindowExceeded"})


class CompactBesideQueueForOpenTests(TakingCase):
    """Finding P-5: queue_for_open answers QUEUE_FOR_OPEN at P16 for a record of any kind (engine/foropen.py, no
    category check, though its definition says usage-limited), and core asks P3 thread_available only where P16 named
    no route (core's engine/dispatch.py) - so compact_continue's hold until the person's /compact is never asked, and
    core's continuation is queued, uncompacted, into a conversation whose context window is full."""
    DEFINITION = COMPACT_CONTINUE
    BESIDE = (QUEUE_FOR_OPEN,)

    def arm(self, plug, state="armed", capability=None, **changes):
        definition = plug.runtime.registry.get(capability or self.cap)
        changes.setdefault("warnings", [str(word) for word in plug.runtime.arming.warnings(definition)])
        return super().arm(plug, state=state, capability=capability, **changes)

    def armed(self, h=None, state="armed"):
        plug = super().armed(h, state=state)
        plug.runtime._code_of(self.DEFINITION)._turns = Turns((h or self.h).home.root)
        return plug

    # Fixed in v0.6.17 (#47): queue_for_open takes up usage-limited records only, so compact's hold is asked again.
    def test_a_full_context_window_is_not_queued_for_open_uncompacted(self):
        plug = self.armed()
        self.failing(CONTEXT_FULL)
        self.h.tick()
        (row,) = self.h.records()
        self.assertEqual(row["category"], "terminal_invalid")
        self.h.backend.loaded_map[T1] = "notLoaded"          # the app runs and does not hold the conversation
        self.h.backend.after_accept = "queue"
        for _ in range(30):
            self.h.tick(advance=60)
        self.assertEqual(self.h.backend.send_calls, [], "held until a compaction turn is the latest")
        self.assertEqual(self.h.record()["last_error"], "notLoaded", "it waits for the app, as A11 says")
        self.assertIsNone(plug.runtime.state.override(row["interruption_id"], QUEUE_FOR_OPEN.id), "never queued")
        self.h.backend.loaded_map[T1] = "loaded"             # opened: compact_continue's hold is asked, and holds
        for _ in range(5):
            self.h.tick(advance=60)
        self.assertEqual(self.h.backend.send_calls, [], "held in the app until the person compacts")
        self.assertIn((JournalCode.ACTED, Point.GATES, Alternative.HOLD), self.journal(plug))

    def test_a_usage_limited_conversation_is_still_queued_for_open_beside_it(self):
        plug = self.armed()
        self.ready_after_reset(loaded=False)
        self.h.backend.loaded_map[T1] = "notLoaded"
        self.h.backend.after_accept = "queue"
        self.h.tick()
        self.assertEqual(self.h.record()["state"], "queued", self.h.record()["last_error"])
        self.assertEqual(len(self.h.backend.send_calls), 1)
        self.assertEqual([spend[0] for spend in self.spends(plug)], [QUEUE_FOR_OPEN.id])


class GoalBesideQueueForOpenTests(GoalCase):
    """Finding P-4: goal_continuation sets a conversation's goal active at P16 and says the goal and the standard
    continuation never both run (its P3 thread_available hold). Once the goal reads active its P16 answers DEFER, the
    next armed answer - queue_for_open's - is taken, and core never asks P3 thread_available for a P16 answer: the
    standard continuation is queued for open beside the goal Codex carries on when the app opens the conversation."""
    registry = (GOAL_CONTINUATION, QUEUE_FOR_OPEN)
    # A measurement neither capability rests on, standing in for MQG where the vocabulary does not have it yet.
    STAND_IN = Measurement.MN

    def both(self):
        plug, fake = self.armed()
        definition = plug.runtime.registry.get(QUEUE_FOR_OPEN.id)
        self.arm(plug, capability=QUEUE_FOR_OPEN.id,
                 warnings=[str(word) for word in plug.runtime.arming.warnings(definition)])
        plug.runtime._code_of(QUEUE_FOR_OPEN)._home = self.h.home.root      # the harness's goals, never this PC's
        self.h.backend.after_accept = "queue"
        self.h.tick()
        self.assertEqual(len(fake.sets()), 1, "the goal set active")
        for _ in range(25):
            self.h.tick(advance=61)
        self.assertEqual(self.status(), "active")
        return plug, fake

    def qfo_journal(self, plug):
        return [line["code"] for line in plug.runtime.state.journal(capability=QUEUE_FOR_OPEN.id)]

    def assert_one_continuation(self, plug, code):
        self.assertEqual(self.h.backend.send_calls, [], "the standard continuation is not queued beside the goal")
        self.assertEqual([spend[0] for spend in self.spends(plug)], [GOAL_CONTINUATION.id], "the goal carried it")
        self.assertEqual(self.qfo_journal(plug).count(code), 1, "why it stood aside, once")

    def assert_both(self, plug):
        self.assertEqual(len(self.h.backend.send_calls), 1, "queued for opening beside the goal: MQG ran it once")
        self.assertEqual(self.h.record()["state"], "queued")
        self.assertEqual(sorted(spend[0] for spend in self.spends(plug)), [GOAL_CONTINUATION.id, QUEUE_FOR_OPEN.id])
        self.assertNotIn("qfo.goal_unmeasured", self.qfo_journal(plug))

    # Fixed in v0.6.17 (#47): while MQG has no pass on this Codex, queue_for_open leaves an active goal to carry it.
    def test_a_goal_set_active_is_not_also_queued_for_open(self):
        plug, _fake = self.both()
        self.assert_one_continuation(plug, "qfo.goal_unmeasured")

    def test_measured_as_two_turns_it_still_stands_aside_and_says_so(self):
        self.measured[self.STAND_IN] = (Verdict.FAIL, ENGINE)
        with patch.object(foropen, "MQG", self.STAND_IN):
            plug, _fake = self.both()
        self.assert_one_continuation(plug, "qfo.goal_two_turns")

    def test_measured_as_one_turn_both_apply(self):
        self.measured[self.STAND_IN] = (Verdict.PASS, ENGINE)
        with patch.object(foropen, "MQG", self.STAND_IN):
            plug, _fake = self.both()
        self.assert_both(plug)

    def test_one_turn_on_another_codex_is_not_measured_here(self):
        self.measured[self.STAND_IN] = (Verdict.PASS, "codex-cli 0.1.0")
        with patch.object(foropen, "MQG", self.STAND_IN):
            plug, _fake = self.both()
        self.assert_one_continuation(plug, "qfo.goal_unmeasured")

    @unittest.skipUnless(hasattr(Measurement, "MQG"), "Measurement.MQG arrives with v0617-queue")
    def test_mqg_passed_by_its_own_id_and_both_apply(self):
        self.assertIs(foropen.MQG, Measurement.MQG)
        self.measured[Measurement.MQG] = (Verdict.PASS, ENGINE)
        plug, _fake = self.both()
        self.assert_both(plug)


class GoalBesideOtherSessionsTests(GoalCase):
    """Finding P-3: goal_continuation's channel at P5 (M2b passed, the goal paused by the usage limit) is a send of a
    conversation the app holds; for one another Codex session holds, other_sessions' TO_SESSION goes only core's
    ordinary way (core's engine/foropen._not_for_open), so a channel named there left the record waiting "held by
    another session" for ever. Settled by the runtime's rule for answers core cannot carry together (runtime.CONFLICTS,
    v0.6.17 #42, branch v0617-queue): the goal's channel stands aside for that send, `overruled` in its journal - goal.py
    is unchanged. Until that rule is merged the session test is skipped; it fails on a runtime without it."""
    registry = (GOAL_CONTINUATION, OTHER_SESSIONS)

    def fresh(self, **kwargs):
        # Who holds a conversation "elsewhere", as the real Backend keeps it (tests/sessionsim.py).
        made = super().fresh(**kwargs)
        holding_sessions(made.backend)
        return made

    def both(self, loaded):
        self.measured[Measurement.M2B] = (Verdict.PASS, ENGINE)
        plug, fake = self.armed(loaded=loaded)
        definition = plug.runtime.registry.get(OTHER_SESSIONS.id)
        self.arm(plug, capability=OTHER_SESSIONS.id,
                 warnings=[str(word) for word in plug.runtime.arming.warnings(definition)])
        return plug, fake

    @unittest.skipUnless(hasattr(runtime, "CONFLICTS"), "runtime.CONFLICTS (v0617-queue, #42) settles P-3: not merged")
    def test_a_conversation_another_session_holds_is_sent_for_it_to_take(self):
        plug, fake = self.both(loaded=False)
        self.h.backend.loaded_map[T1] = "elsewhere"          # a terminal's or VS Code's session holds it
        self.h.backend.after_accept = "queue"
        self.h.tick()
        row = self.h.record()
        self.assertEqual(row["state"], "queued", row["last_error"])
        self.assertEqual(len(self.h.backend.send_calls), 1, "core's own send, for that session to take")
        self.assertEqual(machine.decode_gates(row["gate_eval"])["thread_available"], (machine.PASS, machine.SESSION))
        self.assertEqual(fake.sets(), [], "the goal is not set for a conversation the app does not hold")
        self.assertEqual(fake.adds(), [])
        self.assertEqual(self.status(), "usage_limited")
        self.assertEqual([spend[0] for spend in self.spends(plug)], [OTHER_SESSIONS.id])
        self.assertIn((JournalCode.OVERRULED, Point.SENDER, OTHER_SESSIONS.id), self.journal(plug))

    def test_a_conversation_the_app_holds_still_gets_the_goal_s_channel(self):
        plug, fake = self.both(loaded=True)
        self.h.tick()
        self.assert_no_send()
        self.assertEqual(fake.methods(), ["thread/goal/set", "thread/queue/add"])
        self.assertEqual(self.status(), "active")


class SilentBesideMarkerFreeTests(ac.AdvancedCase):
    """Finding P-6: marker_free_continuation answers CLIENT_ID at P15 for every record, before silent_continuation in
    the registry's order, and the first armed answer wins - so a headless route's P15 (core's engine/routes._silent),
    which takes SILENT alone, never gets it: Continue with no words never acts while the marker-free one is on."""

    @unittest.expectedFailure
    def test_a_route_is_answered_silent_with_marker_free_on(self):
        self.compat = ac.view(capability="recovery_turn_tracking")
        runtime = self.runtime(MARKER_FREE, SILENT_CONTINUATION)
        runtime.arming.catalogs = statement.CATALOGS
        for definition in (MARKER_FREE, SILENT_CONTINUATION):
            result = runtime.arming.arm(definition.id, state="armed", revision=definition.revision,
                                        generation=runtime.state.meta()["generation"], acknowledged_version=ac.ENGINE,
                                        warnings=[str(word) for word in runtime.arming.warnings(definition)],
                                        actor=Actor.DASHBOARD)
            self.assertTrue(result["done"], result)
        runtime.states(fresh=True)
        record = {"interruption_id": ac.KEY, "thread_id": ac.THREAD, "category": "usage_limit"}
        self.assertIs(runtime.ask(Point.DELIVERY, record), Alternative.SILENT)


class PauseBesideResetCreditTests(UsageCase):
    """Finding P-8: usage_pause holds every core record (P3 HOLD) until the meter's next reading shows the window reset
    (engine/usage.py, _mark and holding), and the meter reads only while the Codex app runs, every Poll minutes (15 by
    default). reset_credit's spend resets the window and answers EARLY for fifteen minutes (engine/credits.py): with no
    reading in them, every one of those minutes is held, and the credit spent buys no early look."""

    def setUp(self):
        ac.AdvancedCase.setUp(self)
        self.compat = {"status": "ok", "engine": {"found": True, "version": ac.ENGINE},
                       "capabilities": {name: {"state": "COMPATIBLE", "reason": "local_checks_passed"}
                                        for name in ("usage_probe", "exact_thread_recovery")}}
        self.rt = self.runtime(RESET_CREDIT, USAGE_METER, USAGE_PAUSE)
        self.rt.arming.catalogs = statement.CATALOGS
        self.answer, self.calls, self.app = reply(), [], True
        code = self.rt._code_of(USAGE_METER)
        code._session = lambda: Session(self.answer, self.calls)
        code._app_running = lambda: self.app

    # Fixed in v0.6.17 (#44): a reset spend of the held window lets the pause go (engine/usage.py).
    def test_a_credit_spent_is_not_held_for_its_whole_early_window(self):
        self.on("usage_pause")
        self.on("reset_credit")
        self.answer = reply(five=100)
        self.look()
        self.look()                                   # the pause's own tick marks the window
        record = {"interruption_id": ac.KEY, "thread_id": ac.THREAD, "category": "usage_limit",
                  "state": "waiting_reset"}
        self.assertIs(self.rt.ask(Point.GATES, "submission_safe", record, {}), Alternative.HOLD)
        # What reset_credit's look writes when Codex resets the window for its credit.
        spend = self.rt.state.add_credit_spend(1, "codex", 300, 0, str(uuid.uuid4()), at=self.now)
        self.assertTrue(self.rt.state.finish_credit_spend(spend, SpendOutcome.RESET, at=self.now))
        self.app = False                              # the Codex app closed: the meter reads nothing
        self.assertIs(self.rt.ask(Point.SCHEDULE, record, self.now + 3600), Alternative.EARLY)
        held = []
        for _ in range(15):
            self.now += 60
            self.look()
            held.append(self.rt.ask(Point.GATES, "submission_safe", record, {}) is Alternative.HOLD)
        self.assertFalse(all(held), "some minute of the credit's early window is not held")


if __name__ == "__main__":
    unittest.main()
