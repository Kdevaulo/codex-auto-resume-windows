"""Several conversations at once (v0.6.15-beta): P12's answer, how many sends may wait for their receipts at once,
and what turns it off.

Held against the shipped definition and statement and against core's own engine, store and simulated Codex home
(takingcase.py), with a worker store the harness's engine opens of its own: off, every send goes one after another;
watched, it only journals; on, it answers 2 - the person's Workers only once MQ passed on the Codex in force - for as
long as its units last, and each pooled claim pays one; a pooled send whose fate cannot be known turns it off (K7),
which it would not if the claim were not told the send was pooled.

    PYTHONPATH=src python -m unittest discover -s advanced/tests
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from takingcase import TakingCase  # noqa: E402
from codex_auto_resume.domain.plug import DEFER, Point  # noqa: E402
from codex_auto_resume.store import Store  # noqa: E402
from codex_auto_resume_advanced.engine.parallel import ParallelDispatch  # noqa: E402
from codex_auto_resume_advanced.registry import PARALLEL_DISPATCH  # noqa: E402
from codex_auto_resume_advanced.vocabulary import (ArmingState, JournalCode, Measurement, OffReason,  # noqa: E402
                                                   OptionKey, Verdict)
from advancedcase import ENGINE  # noqa: E402

T1 = "11111111-1111-7111-8111-111111111111"
T2 = "22222222-2222-7222-8222-222222222222"
TURN = "aaaaaaaa-aaaa-7aaa-8aaa-aaaaaaaaaaaa"


class ParallelCase(TakingCase):
    DEFINITION = PARALLEL_DISPATCH

    def arm(self, plug, state="armed", capability=None, **changes):
        """Armed as a person arms it: confirming the warnings its statement shows - MQ unmeasured, until it passes."""
        definition = plug.runtime.registry.get(capability or self.cap)
        changes.setdefault("warnings", [str(word) for word in plug.runtime.arming.warnings(definition)])
        return super().arm(plug, state=state, capability=capability, **changes)

    def due(self, h=None, threads=(T1, T2)):
        """Two conversations' usage-limited turns, detected and past their reset, each loaded."""
        h = h or self.h
        h.engine.open_store = lambda: Store(h.root, check=False)
        for thread in threads:
            h.backend.loaded_map[thread] = "loaded"
            h.home.fail_usage(thread, TURN)
        h.tick()
        from codexsim import RESET
        h.now = RESET + 61
        return h.store.records_in({"waiting_reset", "waiting_poll"})

    def workers(self, plug, h=None):
        h = h or self.h
        return h.engine.plug.partition(h.store.records_in({"waiting_reset", "waiting_poll"}))


class AnswerTests(ParallelCase):
    def test_off_it_is_one_after_another(self):
        self.plugged(self.advanced())
        self.due()
        self.assertEqual(self.workers(None), 1)

    def test_watched_it_only_journals(self):
        plug = self.armed(state="shadow")
        self.due()
        self.assertEqual(self.workers(plug), 1)
        self.assertIn((JournalCode.WOULD_HAVE, Point.CONCURRENCY, Point.CONCURRENCY), self.journal(plug))

    def test_on_it_answers_two(self):
        plug = self.armed()
        self.due()
        self.assertEqual(self.workers(plug), 2)

    def test_more_than_two_only_once_mq_passed_on_this_codex(self):
        plug = self.armed()
        self.choose(plug, OptionKey.WORKERS, 4)
        self.due()
        self.assertEqual(self.workers(plug), 2, "unmeasured: the narrowed route")
        self.measured = {Measurement.MQ: (Verdict.PASS, ENGINE)}
        plug.runtime.states(fresh=True)
        self.assertEqual(self.workers(plug), 4)
        self.measured = {Measurement.MQ: (Verdict.PASS, "another Codex")}
        self.assertEqual(self.workers(plug), 2, "a pass speaks for the Codex it was made on")

    def test_no_units_left_is_one_after_another(self):
        plug = self.armed()
        self.fill(plug, PARALLEL_DISPATCH.ceilings.per_day, thread=lambda index: "%08x-0000-7000-8000-000000000000" % index)
        self.due()
        self.assertEqual(self.workers(plug), 1)

    def test_its_code_reads_only_its_option_and_the_measurement(self):
        code = ParallelDispatch(None)
        self.assertIs(code.partition([{}, {}]), DEFER, "unbound: nothing")


class PaidTests(ParallelCase):
    def test_each_pooled_claim_pays_one(self):
        plug = self.armed()
        self.due()
        self.h.tick()
        paid = [row for row in self.spends(plug) if row[0] == self.cap]
        self.assertEqual(sorted(thread for _cap, thread, _key in paid), [T1, T2])
        self.assertEqual(sorted(call[0] for call in self.h.backend.send_calls), [T1, T2], "each sent once")

    def test_a_pooled_send_whose_fate_is_unknown_turns_it_off(self):
        """Fails with CONCURRENCY not carried by the claim: nothing pays for a pooled send, and nothing trips."""
        plug = self.armed()
        self.due()
        self.h.backend.default_outcome = "unknown"
        self.h.tick()
        self.h.tick(advance=1)
        states = plug.runtime.states(fresh=True)
        self.assertEqual(states.get(self.cap, ArmingState.OFF), ArmingState.OFF)
        arming = plug.runtime.state.arming().get(self.cap)
        self.assertEqual(arming["reason"], OffReason.SUBMISSION_UNKNOWN)


if __name__ == "__main__":
    unittest.main()
