"""v0.6.26 (update resilience, proposal 3): detection that cannot read Codex is said, not only logged.

A Codex update that renames a column of its history, or moves its engine where discovery does not look while the app
is closed, left the watcher reading nothing: every tick logged "detection_unavailable_no_submission" or "initialising
Codex adapter failed", no record was ever made to carry a word, and nothing a person sees changed. Now three ticks of
it, while a process of the Codex app runs, are the watcher's word (domain/public.py WORDS), shown as attention even with
no record, as a watcher not ticking is.

No test asks this PC anything: the process list is a stub throughout.
"""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import patch

_HERE = str(Path(__file__).resolve().parent)
for entry in (str(Path(_HERE).parent / "src"), _HERE):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from codex_auto_resume.domain import public  # noqa: E402
from codex_auto_resume.runtime import loop  # noqa: E402
from codex_auto_resume.ui.popup import model as popup  # noqa: E402
from test_engine import EngineCase  # noqa: E402
from test_recovery_blocked import Store, Watcher  # noqa: E402


class DetectionTests(EngineCase):
    def setUp(self):
        super().setUp()
        self.watcher = Watcher(self.root / "product")
        self.runs = True
        stub = patch.object(loop, "app_running_now", side_effect=lambda: self.runs)
        stub.start()
        self.addCleanup(stub.stop)

    def ticks(self, count, engine):
        for _ in range(count):
            if engine is not None:
                self.h.tick(advance=30)
            self.watcher._self_check(Store([]), engine, 500.0)
        return json.loads(self.watcher.paths.self_check_file.read_text(encoding="utf-8"))["blocked"]

    def break_history(self):
        # Codex's history without the column every failed turn is read from.
        connection = sqlite3.connect(self.h.home.root / "thread_history_1.sqlite")
        try:
            connection.execute("ALTER TABLE thread_turns DROP COLUMN error_json")
            connection.commit()
        finally:
            connection.close()

    def test_a_history_without_error_json_is_said_after_three_ticks(self):
        self.break_history()
        self.assertIsNone(self.ticks(2, self.h.engine))
        self.assertIs(self.h.engine.detection_failed, True)
        self.assertEqual(self.ticks(1, self.h.engine), "detection_blocked:history_unreadable")
        self.assertTrue(any(entry[1] == "detection_unavailable_no_submission" for entry in self.h.logs))
        check = public.self_check(json.loads(self.watcher.paths.self_check_file.read_text(encoding="utf-8")), 500.0)
        status = {"watcher_running": True, "enabled": True, "watcher": {"running": True, "ticking": True,
                                                                        "self_check": check}}
        # Attention with no record at all: nothing was ever detected to carry a word.
        self.assertEqual(popup.activity(status, [], 0.0), "attention")

    def test_a_readable_history_says_nothing(self):
        self.assertIsNone(self.ticks(4, self.h.engine))
        self.assertIs(self.h.engine.detection_failed, False)

    def test_no_engine_for_three_ticks_is_said(self):
        self.assertIsNone(self.ticks(2, None))
        self.assertEqual(self.ticks(1, None), "detection_blocked:engine_missing")

    def test_with_the_app_closed_neither_is_said(self):
        self.runs = False
        self.break_history()
        self.assertIsNone(self.ticks(4, None))
        self.assertIsNone(self.ticks(4, self.h.engine))

    def test_one_good_tick_starts_the_count_again(self):
        self.assertIsNone(self.ticks(2, None))
        self.assertIsNone(self.ticks(1, self.h.engine))
        self.assertIsNone(self.ticks(2, None))


if __name__ == "__main__":
    unittest.main()
