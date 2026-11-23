"""v0.6.26 third round O1 (the owner's logs): a usage meter look that does not read says why, in its journal.

From 2026-11-20 18:12 the owner's meter read nothing for 45 hours with the Codex app running at four sittings, and left
no trace: `look` returned before reading wherever `_running()` was false, journalling nothing, so a meter that never read
looked like a meter with nothing to do. Now each look that does not read journals why - app_closed, unmatched (the app
runs, and no Codex server of the engine the watcher drives was paired with it) or no_engine (no backend for that engine)
- once for each change of why, and once more after a read.

The backend is a fake: nothing reads this PC's processes or starts codex.exe.

    CODEX_AR_EDITION=advanced PYTHONPATH="src;advanced/src;advanced/tests" python -m unittest test_advanced_usage_meter_skips
"""
from __future__ import annotations

import types
import unittest
from unittest.mock import patch

from codex_auto_resume_advanced import registry
from codex_auto_resume_advanced.engine import usage


class Meter:
    def __init__(self):
        self.on = lambda: True
        self.rows = lambda: {}


class Scoped:
    def __init__(self):
        self.counted, self.meter = [], Meter()

    def now(self):
        return 1000.0

    def count(self, code):
        self.counted.append(code)


class Backend:
    def __init__(self, paired, look):
        self.paired, self.app_look = paired, look

    def app_identity(self):
        return self.paired


class SkipTests(unittest.TestCase):
    def setUp(self):
        self.meter = usage.UsageMeter(types.SimpleNamespace(home="home"))
        self.scoped = Scoped()
        self.meter.bind(self.scoped)

    def looks(self, backend, times=1):
        for _look in range(times):
            if isinstance(backend, Exception):
                with patch.object(usage.inuse, "backend", side_effect=backend):
                    self.meter.look()
            else:
                with patch.object(usage.inuse, "backend", return_value=backend):
                    self.meter.look()

    def test_the_app_running_unpaired_is_said_once(self):
        """Fails with the old look: nothing journalled at all (the owner's 45 hours)."""
        self.looks(Backend(None, "unmatched"), times=3)
        self.assertEqual(self.scoped.counted, ["unmatched"])

    def test_each_change_of_why_is_said(self):
        self.looks(Backend(None, "closed"))
        self.looks(OSError("no engine"), times=2)
        self.looks(Backend(None, "unmatched"))
        self.assertEqual(self.scoped.counted, ["app_closed", "no_engine", "unmatched"])

    def test_after_a_read_the_same_why_is_said_again(self):
        self.looks(Backend(None, "closed"))
        with patch.object(usage.UsageMeter, "_read", side_effect=OSError("no session")):
            self.looks(Backend({"pid": 1}, "matched"))
        self.looks(Backend(None, "closed"))
        self.assertEqual(self.scoped.counted, ["app_closed", "unreadable", "app_closed"])

    def test_the_codes_are_the_meters_own(self):
        """The journal takes only a capability's own codes (state/journal.counted)."""
        for code in usage.SKIPS:
            self.assertIn(code, registry.USAGE_METER.codes)

    def test_a_test_seam_says_nothing(self):
        meter = usage.UsageMeter(types.SimpleNamespace(home="home"), app_running=lambda: False)
        meter.bind(self.scoped)
        meter.look()
        self.assertEqual(self.scoped.counted, [])


if __name__ == "__main__":
    unittest.main()
