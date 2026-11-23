"""v0.6.26 third round A6 and A8: the Python choice's runtimes are swept at a start with no record, and never while a Use
job of any process works on them.

A6: a runtime something still ran from when python_choice was turned off stayed whole (right), but the sweep that was to
take it never came: `supervised` returned before its sweep where there is no record, and `view` refuses while the
capability is off. About 30 MB of an old Python stayed under runtimes\\ until the capability was turned on again.

A8: a watcher start sweeps (`supervised`), and the Use job runs in the Dashboard's bridge, another process: the sweep took
the package being downloaded and the folder being checked, and the person was told a good package failed.

Temporary homes only (test_advanced_python_retire.Case).

    CODEX_AR_EDITION=advanced PYTHONPATH="src;advanced/src;advanced/tests" python -m unittest test_advanced_python_sweep_later
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from codex_auto_resume import chosen_runtime as chosen  # noqa: E402
from codex_auto_resume_advanced.control import pythons  # noqa: E402
from test_advanced_python_retire import NEW, OLD, Case  # noqa: E402

# The mark's name and life, as the module says (read so, a revert proof fails on what the sweep does, not on a name).
BUSY, BUSY_FOR = getattr(pythons, "BUSY", ".busy-"), getattr(pythons, "BUSY_FOR", 3600)


class AStartWithNoRecord(Case):
    def test_it_sweeps_what_was_left_whole(self):
        """Fails with the early DEFER: the old runtime stays for as long as the capability is off."""
        self.runtime_folder(OLD)
        self.assertIsNone(chosen.recorded(self.home))
        self.assertIs(pythons.supervised(self.runtime, {"phase": pythons.PHASE_RUNTIME}), pythons.DEFER)
        self.assertEqual(self.names(), [])

    def test_with_no_runtimes_folder_nothing_is_made(self):
        self.assertFalse(chosen.root(self.home).exists(), "no folder to begin with")
        pythons.supervised(self.runtime, {"phase": pythons.PHASE_RUNTIME})
        self.assertFalse(chosen.root(self.home).exists())


class AUseJobUnderWay(Case):
    def mark(self, version, at=None):
        root = chosen.root(self.home)
        root.mkdir(parents=True, exist_ok=True)
        (root / (BUSY + version)).write_text(json.dumps({"pid": 1, "at": int(time.time()) if at is None else at}),
                                                     encoding="utf-8")

    def test_the_sweep_leaves_its_package_and_folder(self):
        """Fails without the mark: the start's sweep unlinks the package and retires the folder being checked."""
        self.runtime_folder(NEW)
        root = chosen.root(self.home)
        (root / (pythons.INCOMING + NEW + ".zip")).write_bytes(b"zip")
        self.mark(NEW)
        pythons._sweep(self.home, OLD)                    # a watcher's start under the version recorded before
        self.assertEqual(self.names(), sorted([BUSY + NEW, pythons.INCOMING + NEW + ".zip", NEW]))

    def test_another_version_still_goes(self):
        self.runtime_folder(OLD)
        self.runtime_folder(NEW)
        self.mark(NEW)
        pythons._sweep(self.home, None)
        self.assertEqual(self.names(), sorted([BUSY + NEW, NEW]))

    def test_a_stale_mark_is_taken_and_honoured_no_more(self):
        self.runtime_folder(NEW)
        self.mark(NEW, at=int(time.time()) - BUSY_FOR - 1)
        pythons._sweep(self.home, None)
        self.assertEqual(self.names(), [])

    def test_the_job_writes_its_mark_and_takes_it_away(self):
        """Fails without `_busy` around the work: nothing tells another process's sweep that a job is under way."""
        seen = []

        def installed(runtime, offer, hands):
            seen.append(sorted(entry.name for entry in chosen.root(self.home).iterdir()))
            return {"word": pythons.FAILED, "step": pythons.UNPACK, "version": NEW}
        pythons._OFFERS[pythons._home(self.runtime)] = [{"version": NEW, "line": "3.15", "release": 1}]
        self.addCleanup(pythons._OFFERS.pop, pythons._home(self.runtime), None)
        self.addCleanup(pythons._JOBS.pop, pythons._home(self.runtime), None)
        original = pythons._installed
        pythons._installed = installed
        self.addCleanup(setattr, pythons, "_installed", original)
        offered = pythons.offered
        pythons.offered = lambda runtime: True
        self.addCleanup(setattr, pythons, "offered", offered)
        answer = pythons.use(self.runtime, {"version": NEW}, start=lambda job: job())
        self.assertTrue(answer["done"], answer)
        self.assertEqual(seen, [[BUSY + NEW]])
        self.assertEqual(self.names(), [])


if __name__ == "__main__":
    unittest.main()
