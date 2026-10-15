"""A full context window (v0.6.16-beta.4): core takes one up only as Codex's contextWindowExceeded, only where the plug
admits it at P17 - never another invalid request, never in the standard edition - and a compaction turn after it
supersedes nothing of its record, while every other later turn still does (A17).

The engine runs against codexsim with a plug of the test's own (test_plug_points.admitting).
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from test_engine import T1  # noqa: E402
from test_plug_points import PluggedCase, admissions, admitting, failed  # noqa: E402
from codex_auto_resume import failures  # noqa: E402
from codex_auto_resume.domain.plug import Alternative  # noqa: E402

CONTEXT_FULL = json.dumps({"codexErrorInfo": "contextWindowExceeded"})
BAD_REQUEST = json.dumps({"codexErrorInfo": "badRequest"})


class AdmitTests(PluggedCase):
    def test_a_full_context_window_is_put_to_the_plug_and_taken_up(self):
        failed(self.h, CONTEXT_FULL)
        plug = admitting()
        self.plugged(plug)
        self.h.tick()
        (facts,) = admissions(plug)
        self.assertEqual((facts["category"], facts["code"], facts["takes"]),
                         ("terminal_invalid", "contextWindowExceeded", frozenset({Alternative.ADMIT})))
        self.assertEqual([row["category"] for row in self.h.records()], ["terminal_invalid"])

    def test_no_other_invalid_request_is_ever_put_to_it(self):
        """Fails with the code rule reverted: a bad request would be offered too."""
        failed(self.h, BAD_REQUEST)
        plug = admitting()
        self.plugged(plug)
        self.h.tick()
        self.assertEqual(admissions(plug), [])
        self.assertEqual(self.h.records(), [])
        facts = dict(failures.shape("badRequest"), category="terminal_invalid")
        self.assertFalse(failures.admits(facts, Alternative.ADMIT))
        for answer in failures.TAKE_UP - {Alternative.ADMIT}:
            self.assertFalse(failures.admits(dict(facts, code="contextWindowExceeded"), answer), answer)

    def test_the_standard_edition_never_takes_it_up(self):
        failed(self.h, CONTEXT_FULL)
        self.h.tick()
        self.assertEqual(self.h.records(), [])


class CompactionTests(PluggedCase):
    def taken(self, error_json=CONTEXT_FULL):
        failed(self.h, error_json)
        self.plugged(admitting())
        self.h.tick()
        (row,) = self.h.records()
        return row

    def compaction(self, *, with_user=False):
        """A turn after the failure: a compaction alone, or one with a person's message beside it."""
        turn = self.h.home.add_turn(T1, None, "completed", user_text="a message" if with_user else None,
                                    progress=False)
        self.h.home.add_item(T1, turn, "contextCompaction")
        self.h.home.catch_up(T1)
        return turn

    def later(self, row):
        return self.h.source.later_turns(T1, row["ordinal"], self.h.engine.proof(row))

    def test_a_compaction_turn_keeps_the_record_the_one_to_continue(self):
        """Fails with the compaction rule reverted: the compaction would supersede it."""
        row = self.taken()
        self.compaction()
        (turn,) = self.later(row)
        self.assertEqual((turn["kind"], self.h.engine.compaction(row, turn)), ("foreign", True))
        self.assertTrue(self.h.engine.valid_interruption(row))
        self.assertFalse(self.h.engine.foreign(row, turn))

    def test_a_person_s_message_beside_it_supersedes_it(self):
        row = self.taken()
        self.compaction(with_user=True)
        (turn,) = self.later(row)
        self.assertFalse(self.h.engine.compaction(row, turn))
        self.assertFalse(self.h.engine.valid_interruption(row))
        self.assertTrue(self.h.engine.foreign(row, turn))

    def test_for_every_other_record_a_compaction_is_still_someone_elses_turn(self):
        unknown = json.dumps({"codexErrorInfo": "brandNewVariant"})
        row = self.taken(unknown)
        self.compaction()
        (turn,) = self.later(row)
        observed = self.h.source.turn_observation(T1, turn["turn_id"], self.h.engine.proof(row))
        self.assertTrue(observed["compaction_only"], "a compaction alone, as Codex left it")
        self.assertFalse(self.h.engine.compaction(row, turn), "but not this record's to keep")
        self.assertFalse(self.h.engine.valid_interruption(row))
        self.assertTrue(self.h.engine.foreign(row, turn))


if __name__ == "__main__":
    unittest.main()
