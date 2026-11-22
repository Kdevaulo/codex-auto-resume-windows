"""v0.6.26 (review of the third round, V6): the watcher's judge sees the waiting records an edition's plug handed over.

The self-check's recovery rules read only core's own waiting records. A record the running edition's plug keeps in its
own state and hands to core each tick (P2, engine/plugrecords.py) waits there too - at thread_available, notLoaded or
loaded_state_unknown - and never fed the rules: a person whose only waiting work was such a record got no word when
recovery could not work here. Now core keeps each handed record's wait of the tick (Engine.handed_waits) and the judge
reads it beside its own. This lane's plug is a stand-in (test_plug_records); the advanced lane has its own test.

No test asks this PC anything: the Restart Manager is a stub, and the folders are scratch ones.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

_HERE = str(Path(__file__).resolve().parent)
for entry in (str(Path(_HERE).parent / "src"), _HERE):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from codex_auto_resume import machine  # noqa: E402
from codex_auto_resume.runtime import loop  # noqa: E402
from codexsim import APP  # noqa: E402
from test_engine import T1  # noqa: E402
from test_recovery_blocked import Watcher  # noqa: E402
import test_plug_records as plug_records  # noqa: E402  (a module, so its cases are not bound here)


def judged(case, minutes=11):
    """The self-check's word after `minutes` of looks over `case.h` - its engine, its store, a home with no lock folder,
    the app's server paired and holding the newest databases."""
    h = case.h
    h.backend.codex_home = h.home.root
    h.backend.app_look = "matched"
    watcher = Watcher(case.root / "product")
    clock = {"now": 0.0}
    held = lambda *paths: ([{"pid": APP["server"]["pid"], "created": APP["server"]["created"]}]  # noqa: E731
                           if any(Path(path).suffix == ".sqlite" for path in paths) else [])
    with patch.object(loop, "resource_users", side_effect=held), \
            patch.object(loop.time, "time", side_effect=lambda: clock["now"]):
        for step in range(minutes + 1):
            clock["now"] = 1000.0 + 60.0 * step
            watcher._self_check(h.store, h.engine, 500.0)
    case.assertEqual(watcher.failures, [])
    return json.loads(watcher.paths.self_check_file.read_text(encoding="utf-8"))["blocked"]


class HandedTests(plug_records.RecordCase):
    def test_a_handed_record_waiting_not_loaded_feeds_the_judge(self):
        self.assertFalse((self.h.home.root / "thread-writer-locks").exists())
        self.h.backend.loaded_map[T1] = "notLoaded"
        plug = self.plug()
        self.h.tick()
        self.assertEqual(plug.moves[-1], ("waiting", "thread_available", "notLoaded"))
        self.assertEqual(self.h.backend.send_calls, [])
        self.assertEqual(self.h.store.records_in(machine.WAITING, home_key=""), [], "no record of core's waits")
        self.assertEqual(judged(self), "recovery_blocked:locks_unread")
        self.assertEqual(getattr(self.h.engine, "handed_waits", None), {T1: "notLoaded"})

    def test_a_handed_record_that_went_says_nothing(self):
        plug = self.plug()
        self.h.tick()
        self.assertEqual(plug.moves[-1][0], "sent")
        self.assertIsNone(judged(self))
        self.assertEqual(getattr(self.h.engine, "handed_waits", None), {})


if __name__ == "__main__":
    unittest.main()
