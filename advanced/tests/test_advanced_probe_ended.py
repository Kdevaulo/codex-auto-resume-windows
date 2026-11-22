# ADVANCED-EDITION-CODE: in the advanced edition's tree, never the standard one's.
"""v0.6.26: a page probe that gives no answers says why, in every test of its module (pagecase.ended).

Dev run 44990528966 (a documents-only commit): every test of test_advanced_page_scheduled failed "the probe did not run",
the end of the PowerShell's error output after it. The process had been ended by an AccessViolationException in the
window's own message handling (WindowCorner.Reshape under SettingsForm.WndProc), which no job's catch in the probe can
see. Each test now says how the process ended - its exit code, or the time limit it was stopped at - and the exception
first, so a crash, a hang and a probe that could not start are told apart without the log's whole stack.
"""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pagecase  # noqa: E402

CRASH = ("\r\nUnhandled Exception: System.AccessViolationException: Attempted to read or write protected memory.\r\n"
         "   at CodexAutoResume.WindowShape.MemorySink.Put(Int32 y, Int32 x, Int32[] values, Int32 start, Int32 count)\r\n"
         "   at CodexAutoResume.WindowCorner.Reshape(Size size, Int32 dpi, POINT at)\r\n")


class EndedTests(unittest.TestCase):
    def test_a_crash_names_its_exit_code_and_its_exception_first(self):
        run = subprocess.CompletedProcess(["powershell.exe"], -532462766, "", CRASH)
        said = pagecase.ended(run)
        self.assertTrue(said.startswith("the probe did not run: its process ended with exit code 0xE0434352: "
                                        "Unhandled Exception: System.AccessViolationException"), said)
        self.assertIn("WindowCorner.Reshape", said, "and what it wrote, after")

    def test_a_probe_stopped_at_its_limit_says_so(self):
        """A timed-out probe is killed: its exit code is the kill's, so the limit is what says what happened."""
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            run, answers = pagecase.probe(work, work / "no-window.exe", [{"kind": "run", "name": "one"}], timeout=0)
        self.assertEqual(answers, {})
        self.assertTrue(pagecase.ended(run).startswith("the probe did not run: its process was stopped after 0 s"),
                        pagecase.ended(run))

    def test_a_probe_that_cannot_load_the_window_says_how_it_ended(self):
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            run, answers = pagecase.probe(work, work / "no-window.exe", [{"kind": "run", "name": "one"}], timeout=120)
        self.assertEqual(answers, {})
        said = pagecase.ended(run)
        self.assertTrue(said.startswith("the probe did not run: its process ended with exit code 1: "), said)
        self.assertIn("LoadFile", said, "and where it ended, in the probe's own words")


if __name__ == "__main__":
    unittest.main()
