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
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))

import advancedcase as ac  # noqa: E402
from takingcase import TakingCase  # noqa: E402
from test_advanced_goal import GoalCase  # noqa: E402
from test_advanced_usage import Session, UsageCase, reply  # noqa: E402
from codex_auto_resume.domain.plug import Alternative, Point  # noqa: E402
from codex_auto_resume_advanced import statement  # noqa: E402
from codex_auto_resume_advanced.codex.turns import Turns  # noqa: E402
from codex_auto_resume_advanced.registry import (COMPACT_CONTINUE, GOAL_CONTINUATION, MARKER_FREE,  # noqa: E402
                                                 QUEUE_FOR_OPEN, RESET_CREDIT, SILENT_CONTINUATION, USAGE_METER,
                                                 USAGE_PAUSE)
from codex_auto_resume_advanced.vocabulary import Actor, JournalCode, SpendOutcome  # noqa: E402
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

    @unittest.expectedFailure
    def test_a_goal_set_active_is_not_also_queued_for_open(self):
        plug, fake = self.armed()
        definition = plug.runtime.registry.get(QUEUE_FOR_OPEN.id)
        self.arm(plug, capability=QUEUE_FOR_OPEN.id,
                 warnings=[str(word) for word in plug.runtime.arming.warnings(definition)])
        self.h.backend.after_accept = "queue"
        self.h.tick()
        self.assertEqual(len(fake.sets()), 1, "the goal set active")
        for _ in range(25):
            self.h.tick(advance=61)
        self.assertEqual(self.status(), "active")
        self.assertEqual(self.h.backend.send_calls, [], "the standard continuation is not queued beside the goal")


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
