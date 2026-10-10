"""Keep going (v0.6.15-beta): a conversation a person picked keeps going after a turn that ended well, up to the count
they chose - three at most until MK passes - and stops on no progress, a finished plan, an unreadable one, an active
goal, a failed or interrupted turn and the count used; picked in the Dashboard's bridge alone.

Held against the shipped definition and statement and against core's own engine, store and simulated Codex home
(takingcase.py), the capability reading that home's history and a goals database of the test's own.

    PYTHONPATH=src python -m unittest discover -s advanced/tests
"""
from __future__ import annotations

import contextlib
import json
from pathlib import Path
import sqlite3
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from takingcase import TakingCase  # noqa: E402
from advancedcase import ENGINE  # noqa: E402
from codex_auto_resume import continuation, l10n  # noqa: E402
from codex_auto_resume_advanced import statement, surfaces  # noqa: E402
from codex_auto_resume_advanced.engine import keepgoing  # noqa: E402
from codex_auto_resume_advanced.registry import KEEP_GOING  # noqa: E402
from codex_auto_resume_advanced.vocabulary import KeepReason, KeepState, Measurement, Refusal, Verdict  # noqa: E402
from test_engine import T1  # noqa: E402

GOAL_COLUMNS = "thread_id TEXT PRIMARY KEY, goal_id TEXT, status TEXT, updated_at_ms INTEGER, objective TEXT"


class KeepCase(TakingCase):
    DEFINITION = KEEP_GOING

    def arm(self, plug, state="armed", capability=None, **changes):
        definition = plug.runtime.registry.get(capability or self.cap)
        changes.setdefault("warnings", [str(word) for word in plug.runtime.arming.warnings(definition)])
        return super().arm(plug, state=state, capability=capability, **changes)

    def setUp(self):
        super().setUp()
        self.goal(None)

    def goal(self, status):
        with contextlib.closing(sqlite3.connect(self.h.home.root / "goals_1.sqlite")) as db:
            db.execute("CREATE TABLE IF NOT EXISTS thread_goals (%s)" % GOAL_COLUMNS)
            db.execute("DELETE FROM thread_goals")
            if status is not None:
                db.execute("INSERT INTO thread_goals VALUES (?, 'goal-1', ?, 1, 'the goal words')", (T1, status))
            db.commit()

    def on(self, count=3):
        plug = self.armed()
        plug.runtime._code_of(plug.runtime.registry.get(self.cap))._home = self.h.home.root
        self.h.backend.loaded_map[T1] = "loaded"
        self.h.home.add_thread(T1)
        picked = self.bridge(plug, "advanced-keep-going-set", thread_id=T1, count=count)
        self.assertTrue(picked["done"], picked)
        return plug

    def bridge(self, plug, command, **argument):
        if command != "advanced-keep-going":
            argument.setdefault("generation", plug.runtime.state.meta()["generation"])
        return surfaces.bridge(plug.runtime, command, argument)

    def turn(self, status="completed", progress=True):
        return self.h.home.add_turn(T1, status=status, progress=progress, completed=int(self.h.now))

    def plan(self, steps):
        payload = {"type": "plan", "steps": steps}
        with contextlib.closing(sqlite3.connect(self.h.home.root / "thread_history_1.sqlite")) as db:
            db.execute("INSERT INTO thread_items (thread_id, turn_id, item_id, rollout_ordinal, item_json, item_type) "
                       "VALUES (?, 'turn', ?, 999, ?, 'plan')", (T1, "plan-%d" % len(steps), json.dumps(payload)))
            db.commit()

    def look(self, times=3):
        for _ in range(times):
            self.h.tick(advance=61)

    def row(self, plug):
        return plug.runtime.state.keep_going(T1)


class GoesOnTests(KeepCase):
    def test_a_turn_that_ended_well_is_continued_and_counted_at_its_send(self):
        plug = self.on()
        self.turn()
        self.look()
        self.assertEqual(len(self.h.backend.send_calls), 1)
        self.assertTrue(self.h.backend.send_calls[0][1].startswith(statement.CATALOGS.text(keepgoing.WORDS_KEY)))
        self.assertEqual((self.row(plug)["used"], self.row(plug)["state"]), (1, KeepState.ON))

    def test_a_plan_with_steps_left_goes_on(self):
        self.on()
        self.turn()
        self.plan([{"step": "secret step words", "status": "completed"}, {"step": "more", "status": "pending"}])
        self.look()
        self.assertEqual(len(self.h.backend.send_calls), 1)


class StopTests(KeepCase):
    def stopped(self, reason, plug):
        self.assertEqual(self.h.backend.send_calls, [])
        self.assertEqual((self.row(plug)["state"], self.row(plug)["reason"]), (KeepState.DONE, reason))

    def test_no_progress_stops_it(self):
        plug = self.on()
        self.turn(progress=False)
        self.look()
        self.stopped(KeepReason.NO_PROGRESS, plug)

    def test_a_finished_plan_stops_it(self):
        plug = self.on()
        self.turn()
        self.plan([{"step": "a", "status": "completed"}, {"step": "b", "status": "completed"}])
        self.look()
        self.stopped(KeepReason.PLAN_DONE, plug)

    def test_a_plan_whose_steps_cannot_be_read_stops_it(self):
        plug = self.on()
        self.turn()
        with contextlib.closing(sqlite3.connect(self.h.home.root / "thread_history_1.sqlite")) as db:
            db.execute("INSERT INTO thread_items (thread_id, turn_id, item_id, rollout_ordinal, item_json, item_type) "
                       "VALUES (?, 'turn', 'plan-x', 999, ?, 'plan')", (T1, json.dumps({"type": "plan"})))
            db.commit()
        self.look()
        self.stopped(KeepReason.PLAN_UNREADABLE, plug)

    def test_an_active_goal_stops_it(self):
        self.goal("active")
        plug = self.on()
        self.turn()
        self.look()
        self.stopped(KeepReason.GOAL_ACTIVE, plug)

    def test_a_failed_or_interrupted_turn_stops_it(self):
        for status, reason in (("failed", KeepReason.FAILED), ("interrupted", KeepReason.BY_PERSON)):
            with self.subTest(status):
                self.h = self.fresh()
                self.goal(None)
                plug = self.on()
                self.turn(status=status, progress=False)
                self.look(times=1)
                self.assertEqual(self.row(plug)["reason"], reason)

    def test_the_count_used_stops_it_and_three_at_most_until_mk(self):
        """Fails with the cap reverted: a count of five would go on past three on an unmeasured Codex."""
        plug = self.on(count=5)
        with contextlib.closing(sqlite3.connect(plug.runtime.state.path)) as db:
            db.execute("UPDATE keep_going SET used=3 WHERE thread_id=?", (T1,))
            db.commit()
        self.turn()
        self.look()
        self.stopped(KeepReason.COUNT_SPENT, plug)

    def test_measured_it_goes_on_to_the_count(self):
        self.measured = {Measurement.MK: (Verdict.PASS, ENGINE)}
        plug = self.on(count=5)
        with contextlib.closing(sqlite3.connect(plug.runtime.state.path)) as db:
            db.execute("UPDATE keep_going SET used=3 WHERE thread_id=?", (T1,))
            db.commit()
        self.turn()
        self.look()
        self.assertEqual(len(self.h.backend.send_calls), 1)

    def test_turned_off_every_conversation_stops(self):
        plug = self.on()
        self.assertTrue(plug.runtime.arming.disarm(self.cap, actor="dashboard")["done"])
        self.assertEqual((self.row(plug)["state"], self.row(plug)["reason"]), (KeepState.DONE, KeepReason.TURNED_OFF))


class BridgeTests(KeepCase):
    def test_the_dashboard_picks_and_stops_and_is_refused_what_is_not_on_offer(self):
        plug = self.on(count=4)
        listed = self.bridge(plug, "advanced-keep-going")
        self.assertEqual([(row["thread_id"], row["count"], row["allowed"]) for row in listed["rows"]], [(T1, 4, 3)])
        self.assertTrue(listed["count_capped"])
        for argument, refusal in (({"count": 11}, Refusal.KEEP_COUNT_INVALID),
                                  ({"count": 2, "generation": -1}, Refusal.STALE_GENERATION),
                                  ({"count": 2, "thread_id": "not-a-uuid"}, Refusal.INVALID_REQUEST)):
            with self.subTest(argument):
                found = self.bridge(plug, "advanced-keep-going-set", **dict({"thread_id": T1}, **argument))
                self.assertEqual(found["refusal"], refusal)
        self.assertTrue(self.bridge(plug, "advanced-keep-going-stop", thread_id=T1)["done"])
        self.assertEqual(self.row(plug)["reason"], KeepReason.BY_PERSON)

    def test_turned_off_it_cannot_be_picked(self):
        plug = self.advanced()
        found = surfaces.bridge(plug.runtime, "advanced-keep-going-set",
                                {"thread_id": T1, "count": 2, "generation": plug.runtime.state.meta()["generation"]})
        self.assertEqual(found["refusal"], Refusal.NOT_ON)

    def test_no_tool_of_a_model_reaches_it(self):
        self.assertFalse([tool["name"] for tool in surfaces.TOOLS if "keep" in tool["name"]])


class WordsTests(unittest.TestCase):
    def test_the_words_pass_as_a_continuation_in_every_language(self):
        for locale in l10n.LOCALES:
            with self.subTest(locale):
                continuation.validate_continuation(statement.CATALOGS.own(locale)[keepgoing.WORDS_KEY])

    def test_allowed_holds_the_count_to_three_until_mk(self):
        self.assertEqual([keepgoing.allowed(count, False) for count in (1, 3, 5, 10)], [1, 3, 3, 3])
        self.assertEqual([keepgoing.allowed(count, True) for count in (1, 3, 5, 10)], [1, 3, 5, 10])


if __name__ == "__main__":
    unittest.main()
