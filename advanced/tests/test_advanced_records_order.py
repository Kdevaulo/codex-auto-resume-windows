"""P2's eight (v0.6.15-beta, design 11c): what the runtime hands core of the edition's own records, in order - those in
flight first, the longest in flight first, from a place that moves on each tick when there are more than core takes;
then one due record of each capability in the registry's order; then the rest - so no capability waits behind another
for more than a tick.

    PYTHONPATH=src python -m unittest discover -s advanced/tests
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from takingcase import TakingCase  # noqa: E402
from codex_auto_resume.domain.plughands import RECORDS_LIMIT  # noqa: E402
from codex_auto_resume_advanced.registry import EMPTY_RESPONSE, RESET_MESSAGE  # noqa: E402
from codex_auto_resume_advanced.vocabulary import RecordState  # noqa: E402

THREAD = "0a1b2c3d-0001-7000-8000-%012d"


def flying(n):
    return {"record_id": "%064x" % (100 + n), "thread_id": THREAD % n, "ordinal": 1, "finished_at": None,
            "record_state": RecordState.IN_FLIGHT, "claimed_at": 1_790_000_000 + n, "launching_at": None,
            "queue_id": None, "withdraw": 0}


def due(word, n):
    return {"record_id": "%064x" % (1000 + n), "thread_id": THREAD % (500 + n), "state": "waiting", "words": word,
            "marker": "m", "sent_at": None, "purpose": "continuation", "ordinal": 1}


class OrderTests(TakingCase):
    DEFINITION = EMPTY_RESPONSE
    BESIDE = (RESET_MESSAGE,)

    def arm(self, plug, state="armed", capability=None, **changes):
        definition = plug.runtime.registry.get(capability or self.cap)
        changes.setdefault("warnings", [str(word) for word in plug.runtime.arming.warnings(definition)])
        return super().arm(plug, state=state, capability=capability, **changes)

    def runtime(self, in_flight, answers):
        plug = self.armed()
        runtime = plug.runtime
        runtime.state.messages_in_flight = lambda: []
        runtime.state.continuations_in_flight = lambda: [flying(n) for n in in_flight]
        for capability, records in answers.items():
            code = runtime._code_of(runtime.registry.get(capability))
            type(code).records = lambda self, view, _records=records: list(_records)
        self.addCleanup(self._restore)
        return runtime

    def _restore(self):
        from codex_auto_resume_advanced.engine import emptyreply, resetmessage
        emptyreply.EmptyResponse.records = self._saved[0]
        resetmessage.ResetMessage.records = self._saved[1]

    def setUp(self):
        super().setUp()
        from codex_auto_resume_advanced.engine import emptyreply, resetmessage
        self._saved = (emptyreply.EmptyResponse.records, resetmessage.ResetMessage.records)

    def test_in_flight_first_the_longest_first_and_the_place_moves_on(self):
        runtime = self.runtime([5, 3, 9, 1, 7, 2, 8, 4, 6, 10], {})
        first = runtime.records(None)
        self.assertEqual([record["sent_at"] for record in first][:RECORDS_LIMIT],
                         [1_790_000_000 + n for n in range(1, 9)])
        second = runtime.records(None)
        self.assertEqual(second[0]["sent_at"], 1_790_000_009, "the place moves on by core's eight")

    def test_one_due_of_each_capability_in_the_registrys_order_then_the_rest(self):
        """Fails with the answers joined as they come: the reset messages' second would go before the first
        empty reply."""
        runtime = self.runtime([], {"reset_message": [due("m", 1), due("m", 2)], "empty_response": [due("e", 3)]})
        self.assertEqual([record["words"] for record in runtime.records(None)], ["m", "e", "m"])


if __name__ == "__main__":
    unittest.main()
