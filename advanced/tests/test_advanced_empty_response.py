"""Empty-response recovery (v0.6.15-beta): a turn that ended with no reply is continued once, and a chain of them twice,
judged only by the kinds of item it left; a goal Codex keeps going or stopped is left alone.

Held against the shipped definition and statement and against core's own engine, store and simulated Codex home
(takingcase.py), the capability reading that simulated home's history and a goals database of the test's own.

    PYTHONPATH=src python -m unittest discover -s advanced/tests
"""
from __future__ import annotations

import contextlib
import hashlib
from pathlib import Path
import sqlite3
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from takingcase import TakingCase  # noqa: E402
from codex_auto_resume import continuation, l10n  # noqa: E402
from codex_auto_resume_advanced import statement  # noqa: E402
from codex_auto_resume_advanced.engine import emptyreply  # noqa: E402
from codex_auto_resume_advanced.registry import EMPTY_RESPONSE  # noqa: E402
from codex_auto_resume_advanced.vocabulary import ContinuationReason, RecordState  # noqa: E402
from test_engine import T1  # noqa: E402

GOAL_COLUMNS = "thread_id TEXT PRIMARY KEY, goal_id TEXT, status TEXT, updated_at_ms INTEGER, objective TEXT"


class EmptyCase(TakingCase):
    DEFINITION = EMPTY_RESPONSE

    def arm(self, plug, state="armed", capability=None, **changes):
        """Armed as a person arms it: confirming the warnings its statement shows - ME unmeasured, until it passes."""
        definition = plug.runtime.registry.get(capability or self.cap)
        changes.setdefault("warnings", [str(word) for word in plug.runtime.arming.warnings(definition)])
        return super().arm(plug, state=state, capability=capability, **changes)

    def setUp(self):
        super().setUp()
        self.goals()

    def goals(self, status=None, h=None):
        """The simulated home's goals database, with `thread`'s goal at `status` (none with None)."""
        h = h or self.h
        with contextlib.closing(sqlite3.connect(h.home.root / "goals_1.sqlite")) as db:
            db.execute("CREATE TABLE IF NOT EXISTS thread_goals (%s)" % GOAL_COLUMNS)
            db.execute("DELETE FROM thread_goals")
            if status is not None:
                db.execute("INSERT INTO thread_goals VALUES (?, 'goal-1', ?, 1, 'the goal words')", (T1, status))
            db.commit()

    def on(self, h=None, state="armed"):
        h = h or self.h
        plug = self.armed(h, state=state)
        plug.runtime._code_of(plug.runtime.registry.get(self.cap))._home = h.home.root
        h.backend.loaded_map[T1] = "loaded"
        return plug

    def empty_turn(self, h=None, kinds=("reasoning",)):
        """A turn Codex completed now with the person's message and `kinds`, and no final agent item."""
        h = h or self.h
        turn = h.home.add_turn(T1, progress=False, completed=int(h.now))
        for kind in kinds:
            h.home.add_item(T1, turn, kind)
        return turn

    def settle(self, h=None):
        """Two looks thirty seconds apart and ten after the turn ended, the errand once a minute: then the tick that
        hands what it made to core."""
        h = h or self.h
        h.tick(advance=11)
        h.tick(advance=61)
        h.tick(advance=1)

    def continuations(self, plug):
        return plug.runtime.state.continuations(pending=None)


class FoundTests(EmptyCase):
    def test_reasoning_only_is_empty_and_is_continued_once_in_the_catalogs_words(self):
        plug = self.on()
        self.empty_turn()
        self.settle()
        self.assertEqual(len(self.h.backend.send_calls), 1)
        words = statement.CATALOGS.text(emptyreply.WORDS_KEY)
        self.assertTrue(self.h.backend.send_calls[0][1].startswith(words))
        for _ in range(5):
            self.h.tick(advance=61)
        self.assertEqual(len(self.h.backend.send_calls), 1, "once a turn")

    def test_every_other_kind_is_not_empty(self):
        for kind in ("agentMessage", "commandExecution", "fileChange", "mcpToolCall", "dynamicToolCall",
                     "collabAgentToolCall", "webSearch", "imageGeneration", "contextCompaction", "brandNewKind"):
            with self.subTest(kind):
                h = self.fresh()
                self.goals(h=h)
                self.on(h)
                self.empty_turn(h, kinds=("reasoning", kind))
                self.settle(h)
                self.assertEqual(h.backend.send_calls, [])

    def test_it_settles_first_ten_seconds_and_two_looks_thirty_apart(self):
        plug = self.on()
        self.empty_turn()
        self.h.tick(advance=5)                           # five seconds after it ended: not yet
        self.h.tick(advance=1)
        self.assertEqual(self.continuations(plug), [])
        self.h.tick(advance=61)                          # the first look that counts
        self.assertEqual(self.continuations(plug), [], "one look is not two")
        self.h.tick(advance=61)
        self.assertEqual(len(self.continuations(plug)), 1)

    def test_off_or_watched_it_does_nothing(self):
        self.plugged(self.advanced())
        self.empty_turn()
        self.settle()
        self.assertEqual(self.h.backend.send_calls, [])
        h = self.fresh()
        self.goals(h=h)
        plug = self.on(h, state="shadow")
        self.empty_turn(h)
        self.settle(h)
        self.assertEqual(h.backend.send_calls, [])
        self.assertEqual(plug.runtime.state.continuations(pending=None), [])


class ChainTests(EmptyCase):
    def test_a_chain_has_two_continuations_and_its_third_is_not_made(self):
        """Fails with the chain's count reverted: every empty turn would be continued."""
        plug = self.on()
        self.h.backend.after_accept = "queue"
        self.empty_turn()
        sent = 0
        for _ in range(3):
            for _ in range(40):
                self.h.tick(advance=61)
                if len(self.h.backend.send_calls) > sent:
                    break
            if len(self.h.backend.send_calls) == sent:
                break
            sent = len(self.h.backend.send_calls)
            self.h.home.dispatch(T1, progress=False, completed=int(self.h.now))   # Codex runs it: no reply again
            self.h.tick(advance=6)
            self.h.tick(advance=10)
        self.assertEqual(sent, 2, "two continuations in one chain")
        reasons = [row["reason"] for row in self.continuations(plug)]
        self.assertIn(ContinuationReason.CHAIN_SPENT, reasons)


class GoalTests(EmptyCase):
    def test_an_active_or_blocked_goal_is_left_alone_and_never_written(self):
        for status in ("active", "blocked"):
            with self.subTest(status):
                h = self.fresh()
                self.goals(status, h=h)
                before = hashlib.sha256((h.home.root / "goals_1.sqlite").read_bytes()).hexdigest()
                plug = self.on(h)
                self.empty_turn(h)
                self.settle(h)
                self.assertEqual(h.backend.send_calls, [])
                self.assertEqual([row["reason"] for row in plug.runtime.state.continuations(pending=None)],
                                 [ContinuationReason.GOAL_LEFT])
                self.assertEqual(hashlib.sha256((h.home.root / "goals_1.sqlite").read_bytes()).hexdigest(), before)

    def test_a_paused_goal_is_continued(self):
        self.goals("paused")
        self.on()
        self.empty_turn()
        self.settle()
        self.assertEqual(len(self.h.backend.send_calls), 1)

    def test_goals_that_cannot_be_read_leave_it_to_the_standard_edition(self):
        (self.h.home.root / "goals_1.sqlite").unlink()
        plug = self.on()
        self.empty_turn()
        self.settle()
        self.assertEqual(self.h.backend.send_calls, [])
        self.assertEqual(self.continuations(plug), [])


class MeasureTests(EmptyCase):
    def test_me_reads_whether_the_turn_was_empty_and_never_a_word(self):
        from types import SimpleNamespace
        from codex_auto_resume_advanced import measure
        from codex_auto_resume_advanced.vocabulary import Measurement, Verdict
        self.empty_turn()
        ctx = measure.Context(Measurement.ME, backend=SimpleNamespace(codex_home=self.h.home.root), thread=T1)
        verdict, observed, _note = measure._me(ctx)
        self.assertEqual(verdict, Verdict.BLOCKED, "the person says whether it was a turn with no reply")
        self.assertEqual(observed, {"history_read": True, "turn_found": True, "completed": True,
                                    "final_agent": False, "empty_kinds_only": True})
        verdict, observed, _note = measure._me(measure.Context(Measurement.ME, backend=None, thread=T1))
        self.assertEqual(observed, {"history_read": False}, "no Codex home given: nothing read")


class WordsTests(unittest.TestCase):
    def test_the_words_pass_as_a_continuation_in_every_language(self):
        for locale in l10n.LOCALES:
            with self.subTest(locale):
                words = statement.CATALOGS.own(locale)[emptyreply.WORDS_KEY]
                continuation.validate_continuation(words)

    def test_the_handed_record_is_a_continuation_with_its_turns_ordinal(self):
        from codex_auto_resume_advanced.engine.continued import handed
        row = {"record_id": "%064x" % 5, "thread_id": T1, "ordinal": 7, "finished_at": None,
               "record_state": RecordState.WAITING, "words": "Carry on."}
        found = handed(row)
        self.assertEqual((found["purpose"], found["ordinal"], found["state"]), ("continuation", 7, "waiting"))


if __name__ == "__main__":
    unittest.main()
