"""Compact a full conversation, then continue (v0.6.16-beta.4): a turn that failed on Codex's context window is taken
up for that one code, held while the app has the conversation until a compaction turn is the latest - then
continued once by core's ordinary send - and, where nothing holds it and Codex is closed, compacted and continued on
the headless route.

Held against the shipped definition and statement and against core's own engine, store and simulated Codex home
(takingcase.py); the turns it reads are the harness's Codex home's.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from takingcase import TakingCase  # noqa: E402
from advancedcase import ENGINE  # noqa: E402
from codex_auto_resume.domain.plug import DEFER, Alternative, Point  # noqa: E402
from codex_auto_resume_advanced import registry  # noqa: E402
from codex_auto_resume_advanced.codex import headless  # noqa: E402
from codex_auto_resume_advanced.codex.turns import Turn, Turns  # noqa: E402
from codex_auto_resume_advanced.engine.compact import GIVE_UP_SECONDS, CompactContinue  # noqa: E402
from codex_auto_resume_advanced.registry import COMPACT_CONTINUE  # noqa: E402
from codex_auto_resume_advanced.vocabulary import (ArmingState, ArmingWarning, Measurement,  # noqa: E402
                                                   Verdict)
from test_engine import T1  # noqa: E402

CONTEXT_FULL = json.dumps({"codexErrorInfo": "contextWindowExceeded"})
KEY = "%064x" % 7


class CompactCase(TakingCase):
    DEFINITION = COMPACT_CONTINUE

    def arm(self, plug, state="armed", capability=None, **changes):
        definition = plug.runtime.registry.get(capability or self.cap)
        changes.setdefault("warnings", [str(word) for word in plug.runtime.arming.warnings(definition)])
        return super().arm(plug, state=state, capability=capability, **changes)

    def armed(self, h=None, state="armed"):
        plug = super().armed(h, state=state)
        h = h or self.h
        plug.runtime._code_of(self.DEFINITION)._turns = Turns(h.home.root)
        return plug

    def compaction(self, status="completed"):
        turn = self.h.home.add_turn(T1, None, status, user_text=None, progress=False)
        self.h.home.add_item(T1, turn, "contextCompaction")
        self.h.home.catch_up(T1)
        return turn


class AppTests(CompactCase):
    def test_off_a_full_context_window_is_never_taken_up(self):
        self.plugged(self.advanced())
        self.failing(CONTEXT_FULL)
        self.h.tick()
        self.assertEqual(self.h.records(), [])

    def test_held_until_the_person_compacts_then_continued_once(self):
        """Fails with core's compaction rule reverted: the compaction turn would supersede the record."""
        self.armed()
        self.failing(CONTEXT_FULL)
        self.h.tick()
        (row,) = self.h.records()
        self.assertEqual(row["category"], "terminal_invalid")
        for _ in range(15):
            self.h.tick(advance=60)
        self.assertEqual(self.h.backend.send_calls, [], "held, past its wait, while the failed turn is the latest")
        self.compaction()
        for _ in range(3):
            self.h.tick(advance=60)
        self.assertEqual(len(self.h.backend.send_calls), 1, "the ordinary continuation, once")
        self.assertNotIn(self.h.record()["state"], ("superseded", "superseded_by_user"))
        self.assertNotIn("not_taken_up", [line[1] for line in self.h.logs], "taken up, so never said passed over")


class CodeTests(unittest.TestCase):
    class Scoped:
        def __init__(self, now, taken):
            self._now, self._taken = now, taken

        def now(self):
            return self._now

        def admission(self, key):
            return {"created_at": self._taken}

    def code(self, latest, *, now=1000.0, taken=900.0):
        class Reader:
            def latest(self, thread_id):
                return latest
        made = CompactContinue(None, turns=Reader(), session=lambda capability: None,
                               follower=headless.Follower(poll=0.01), app_running=lambda: False)
        made.bind(self.Scoped(now, taken))
        return made

    @staticmethod
    def turn(ordinal, kinds, status="completed"):
        return Turn("0" * 8 + "-0000-0000-0000-" + "0" * 12, status, False, 1, False, ordinal, kinds)

    def record(self, **changes):
        return dict({"interruption_id": KEY, "thread_id": T1, "category": "terminal_invalid", "ordinal": 5,
                     "holder": "none", "app": False}, **changes)

    def test_only_codex_s_own_context_window_code(self):
        code = self.code(None)
        self.assertIs(code.admission({"category": "terminal_invalid", "code": "contextWindowExceeded"}),
                      Alternative.ADMIT)
        for failure in ({"category": "terminal_invalid", "code": "badRequest"},
                        {"category": "unknown", "code": "contextWindowExceeded"}):
            self.assertIs(code.admission(failure), DEFER, failure)

    def test_known_failure_gives_up_after_a_day_or_a_failed_compaction(self):
        compacting = self.turn(6, {"contextCompaction": 1})
        self.assertIs(self.code(compacting).gate("known_failure", self.record(), {}), Alternative.ADMIT)
        self.assertIs(self.code(compacting, now=900.0 + GIVE_UP_SECONDS).gate("known_failure", self.record(), {}),
                      DEFER)
        failed_one = self.turn(6, {"contextCompaction": 1}, status="failed")
        self.assertIs(self.code(failed_one).gate("known_failure", self.record(), {}), DEFER)

    def test_held_in_the_app_until_a_compaction_alone_is_the_latest(self):
        self.assertIs(self.code(self.turn(5, {})).gate("thread_available", self.record(), {}), Alternative.HOLD)
        mixed = self.turn(6, {"contextCompaction": 1, "userMessage": 1})
        self.assertIs(self.code(mixed).gate("thread_available", self.record(), {}), Alternative.HOLD)
        alone = self.turn(6, {"contextCompaction": 1, "reasoning": 2})
        self.assertIs(self.code(alone).gate("thread_available", self.record(), {}), DEFER)

    def test_unheld_it_compacts_here_then_continues_here(self):
        first = self.code(self.turn(5, {})).unloaded(self.record())
        self.assertEqual(first.mode, headless.COMPACT)
        then = self.code(self.turn(6, {"contextCompaction": 1})).unloaded(self.record())
        self.assertEqual(then.mode, headless.TURN)
        for record in (self.record(holder="session", app=True), self.record(category="usage_limit")):
            self.assertIs(self.code(self.turn(5, {})).unloaded(record), DEFER, record)


class RegistryTests(CompactCase):
    def test_it_answers_at_p16_before_headless_run_and_is_shown_after_the_capacity_retry(self):
        at = tuple(d.id for d in registry.REGISTRY.at(Point.UNLOADED))
        self.assertLess(at.index(self.cap), at.index("headless_run"))
        shown = registry.SHOWN_ORDER
        self.assertEqual(shown.index(self.cap), shown.index("capacity_retry") + 1)

    def test_unmeasured_on_this_codex_is_a_warning_never_a_refusal(self):
        plug = self.advanced()
        definition = plug.runtime.registry.get(self.cap)
        self.assertIn(ArmingWarning.UNMEASURED, plug.runtime.arming.warnings(definition))
        self.measured = {word: (Verdict.PASS, ENGINE) for word in (Measurement.M7, Measurement.MX, Measurement.MXA)}
        self.assertNotIn(ArmingWarning.UNMEASURED, plug.runtime.arming.warnings(definition))
        self.measured = {}
        self.arm(plug)
        self.assertEqual(plug.runtime.states(fresh=True)[self.cap], ArmingState.ARMED)


if __name__ == "__main__":
    unittest.main()
