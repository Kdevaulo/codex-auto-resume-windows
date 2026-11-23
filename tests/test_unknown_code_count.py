"""v0.6.26 (review of the fourth round's fixes, R4): the unknown Codex error code is shown with how many failures of
that code came in the last day, not how many of any unknown code.

B9 (amended by the owner on 2026-11-23) says the watcher keeps, for a code this version does not know, "that code ...
and how many in the last day"; Diagnostics shows "{code} ({n} in the last day)", and PLUGIN's watcher.self_check and the
skill say the same. `WatchLoop._unknown_errors` counted every unknown-coded failure under the newest code: one betaFault
after one alphaFault read "betaFault (2 in the last day)". The stored shape stays {"code", "count"}, so an older reader
(v0.6.26-beta) shows the same two fields; its n is now the count of that code alone.

No test asks this PC anything: the history is a stub.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import types
import unittest

_HERE = str(Path(__file__).resolve().parent)
for entry in (str(Path(_HERE).parent / "src"), _HERE):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from codex_auto_resume.domain import public  # noqa: E402
from test_recovery_blocked import Watcher  # noqa: E402

TAGGED = {"form": "tagged", "status": None, "has_message": True}


def failure(code, at):
    return {"category": "unknown", "completed_at": at, "shape": dict(TAGGED, code=code)}


class UnknownCodeCountTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.watcher = Watcher(Path(temp.name) / "product")
        self.asked = []

    def errors(self, rows, now=100000.0):
        def latest_failures(since, **asked):
            self.asked.append(since)
            return [dict(row) for row in rows]
        engine = types.SimpleNamespace(source=types.SimpleNamespace(latest_failures=latest_failures))
        return self.watcher._unknown_errors(engine, now)

    def test_the_reviews_repro_one_beta_fault_after_one_alpha_fault(self):
        """Fails with the fix reverted: {'code': 'betaFault', 'count': 2}."""
        self.assertEqual(self.errors([failure("alphaFault", 100.0), failure("betaFault", 200.0)]),
                         {"code": "betaFault", "count": 1})

    def test_the_newest_codes_own_failures_are_counted(self):
        rows = [failure("betaFault", 100.0), failure("alphaFault", 150.0), failure("betaFault", 300.0),
                failure("gammaFault", 50.0), failure("betaFault", 120.0)]
        self.assertEqual(self.errors(rows), {"code": "betaFault", "count": 3})

    def test_only_the_last_day_is_asked_and_none_says_nothing(self):
        self.assertIsNone(self.errors([]))
        self.assertEqual(self.asked[-1], 100000.0 - 86400.0)

    def test_the_stored_shape_is_what_every_reader_reads(self):
        """selfcheck.json keeps {"code", "count"} as v0.6.26-beta wrote it: the reader of either version takes it."""
        found = self.errors([failure("alphaFault", 100.0), failure("betaFault", 200.0)])
        note = public.self_check_note(500.0, None, found)
        read = public.self_check(json.loads(json.dumps(note)), 500.0)
        self.assertEqual(read["unknown_error"], {"code": "betaFault", "count": 1})


if __name__ == "__main__":
    unittest.main()
